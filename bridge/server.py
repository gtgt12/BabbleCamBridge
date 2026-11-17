"""BabbleCamBridge server: reads several webcams at once and serves each as a low-latency MJPEG stream.

Why: three USB 2.0 cameras opened uncompressed (what most apps do) don't fit through one USB 2.0 hub, so the
third camera fails. This server always asks the cameras for compressed MJPEG, so all of them fit.

Per stream (see config.json): which camera, HTTP port, crop, mirror, anti-flicker (removes the rolling bands a
VR headset's display causes), auto-brightness, light noise smoothing.
  http://127.0.0.1:<port>/        cropped, processed stream  (give this to Babble)
  http://127.0.0.1:<port>/raw     whole picture, same processing, no crop (for aiming / setting the crop)
  http://127.0.0.1:<control>/status   JSON status of all streams
Settings changes in config.json are picked up automatically within about a second."""
import io
import json
import os
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from deflicker import Deflicker  # noqa: E402
from devices import NOWIN, find_camera, find_ffmpeg, list_cameras  # noqa: E402
from config import CONFIG_PATH, LOG_DIR, load_config  # noqa: E402

os.makedirs(LOG_DIR, exist_ok=True)
_log_lock = threading.Lock()


def log(msg):
    line = time.strftime("%Y-%m-%d %H:%M:%S ") + msg
    with _log_lock:
        try:
            with open(os.path.join(LOG_DIR, "server.log"), "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            pass
    if sys.stdout:
        try:
            print(line, flush=True)
        except Exception:
            pass


class Frames:
    """Newest frame only: viewers always get the latest picture, nothing piles up (no growing delay)."""

    def __init__(self):
        self.jpeg = None
        self.seq = 0
        self.cond = threading.Condition()

    def put(self, jpeg):
        with self.cond:
            self.jpeg = jpeg
            self.seq += 1
            self.cond.notify_all()


class Stream(threading.Thread):
    def __init__(self, cfg, ffmpeg):
        super().__init__(daemon=True)
        self.cfg = cfg
        self.ffmpeg = ffmpeg
        self.out = Frames()
        self.raw = Frames()
        self.raw_viewers = 0
        self.status = "starting"
        self.fps = 0.0
        self.proc = None
        self.stop_flag = False
        self.restart_flag = False
        self.httpd = None
        self.host = "127.0.0.1"

    # -- settings ---------------------------------------------------------------------------------
    def capture_key(self, cfg=None):
        c = cfg or self.cfg
        return json.dumps([c.get("camera"), c.get("input")], sort_keys=True)

    def update(self, cfg):
        need_restart = self.capture_key(cfg) != self.capture_key()
        self.cfg = cfg
        if need_restart:
            self.restart_capture()

    def restart_capture(self):
        self.restart_flag = True
        if self.proc and self.proc.poll() is None:
            self.proc.kill()

    def stop(self):
        self.stop_flag = True
        self.restart_capture()
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()

    # -- capture loop -----------------------------------------------------------------------------
    def run(self):
        name = self.cfg["name"]
        while not self.stop_flag:
            self.restart_flag = False
            cam = find_camera(self.cfg.get("camera"))
            if not cam:
                self.status = "no camera selected" if not self.cfg.get("camera") else "waiting for camera"
                self.fps = 0.0
                time.sleep(2)
                continue
            inp = self.cfg.get("input", {})
            w, h = int(inp.get("width", 640)), int(inp.get("height", 480))
            half = bool(inp.get("half_resolution", True))
            ow, oh = (w // 2, h // 2) if half else (w, h)
            cmd = [self.ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error",
                   "-fflags", "nobuffer", "-flags", "low_delay"]
            if half and inp.get("format", "mjpeg") == "mjpeg":
                cmd += ["-lowres", "1"]
            cmd += ["-f", "dshow", "-rtbufsize", "8M", "-vcodec", inp.get("format", "mjpeg"),
                    "-video_size", f"{w}x{h}", "-framerate", str(inp.get("fps", 30)), "-i", "video=" + cam["dshow"]]
            vf = "format=gray" if not half or inp.get("format", "mjpeg") == "mjpeg" else f"scale={ow}:{oh},format=gray"
            cmd += ["-vf", vf, "-fps_mode", "passthrough", "-f", "rawvideo", "pipe:1"]
            errlog = open(os.path.join(LOG_DIR, f"ffmpeg-{name}.log"), "ab")
            try:
                self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=errlog, bufsize=0, creationflags=NOWIN)
            except OSError as e:
                self.status = f"cannot start ffmpeg: {e}"
                time.sleep(3)
                continue
            log(f"[{name}] camera started: {cam['name']} {cam['location']}")
            self.status = "running"
            try:
                self._process(self.proc, ow, oh)
            except Exception as e:  # keep the server alive whatever happens in one stream
                log(f"[{name}] processing error: {e!r}")
            if self.proc.poll() is None:
                self.proc.kill()
            self.proc.wait()
            errlog.close()
            if not self.stop_flag and not self.restart_flag:
                log(f"[{name}] camera stopped, retrying in 2 s")
                self.status = "camera lost, retrying"
                self.fps = 0.0
                time.sleep(2)

    def _process(self, proc, w, h):
        n = w * h
        deflicker = None
        prev = None
        gain = 1.0
        t_count, count = time.time(), 0
        while not self.stop_flag and not self.restart_flag:
            buf = bytearray()
            while len(buf) < n:
                chunk = proc.stdout.read(n - len(buf))
                if not chunk:
                    return
                buf += chunk
            c = self.cfg
            f = np.frombuffer(bytes(buf), np.uint8).reshape(h, w)
            if c.get("mirror"):
                f = f[:, ::-1]
            if c.get("antiflicker"):
                if deflicker is None:
                    deflicker = Deflicker(h, w, period=int(c.get("antiflicker_period", 5)), thr=0.15, beta=0.12)
                img = deflicker.process_f(np.ascontiguousarray(f))
            else:
                deflicker = None
                img = f.astype(np.float32)
            if c.get("smoothing", False):
                # motion-adaptive: small changes (noise) are averaged, real movement passes at once
                if prev is None or prev.shape != img.shape:
                    prev = img
                else:
                    d = img - prev
                    k = np.abs(d) * np.float32(1 / 14.0)
                    np.clip(k, 0.4, 1.0, out=k)
                    prev = prev + d * k
                img = prev
            else:
                prev = None
            x, y, cw, ch = crop_box(c.get("crop"), w, h)
            if c.get("auto_brightness"):
                s = img[y:y + ch:4, x:x + cw:4].ravel()
                i90 = int(s.size * 0.9)
                p90 = float(np.partition(s, i90)[i90])
                black = float(c.get("black_level", 7))
                want = min(max(float(c.get("brightness_target", 170)) / max(p90 - black, 4.0), 0.5), 12.0)
                gain += (0.6 if abs(want / gain - 1) > 0.12 else 0.15) * (want - gain)
                img = (img - np.float32(black)) * np.float32(gain)
            full = np.clip(img + 0.5, 0, 255).astype(np.uint8)
            self.out.put(encode(full[y:y + ch, x:x + cw], c.get("jpeg_quality", 85)))
            if self.raw_viewers > 0:
                self.raw.put(encode(full, 80))
            count += 1
            now = time.time()
            if now - t_count >= 2:
                self.fps = count / (now - t_count)
                t_count, count = now, 0


def crop_box(crop, w, h):
    """crop = [x, y, width, height] in output pixels (after half resolution / mirror); None = whole picture."""
    if not crop:
        return 0, 0, w, h
    x, y, cw, ch = (int(v) for v in crop)
    x, y = max(0, min(x, w - 8)), max(0, min(y, h - 8))
    return x, y, max(8, min(cw, w - x)), max(8, min(ch, h - y))


def request_allowed(handler, host="127.0.0.1"):
    """Only answer requests meant for this PC, and never requests a web page makes from its own script.
    - Host check: blocks 'DNS rebinding' tricks where a website pretends to be 127.0.0.1.
    - Origin check: a web page's fetch/XHR carries an Origin header; Babble, the window app and <img>/viewer pages
      don't. No CORS headers are sent either, so web pages can't read pictures or status."""
    hostname = (handler.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]").lower()
    allowed = {"127.0.0.1", "localhost", "::1"}
    if host not in ("127.0.0.1", "localhost", "0.0.0.0", ""):
        allowed.add(host.lower())
    if host == "0.0.0.0":  # user chose to share on the local network: allow any private address
        allowed.add(hostname) if hostname.startswith(("192.168.", "10.", "172.")) else None
    origin = handler.headers.get("Origin")
    if hostname not in allowed or (origin and origin != "null"):
        handler.send_error(403, "forbidden")
        return False
    return True


def encode(arr, q):
    b = io.BytesIO()
    Image.fromarray(arr, "L").save(b, "JPEG", quality=int(q))
    return b.getvalue()


def mjpeg_handler(stream):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            if not request_allowed(self, stream.host):
                return
            path = self.path.split("?")[0]
            if path == "/snapshot.jpg":
                jpg = stream.out.jpeg
                if jpg is None:
                    self.send_error(503, "no picture yet")
                    return
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(jpg)))
                self.end_headers()
                self.wfile.write(jpg)
                return
            if path not in ("/", "/raw"):
                self.send_error(404)
                return
            src = stream.raw if path == "/raw" else stream.out
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            if path == "/raw":
                stream.raw_viewers += 1
            last = -1
            try:
                while not stream.stop_flag:
                    with src.cond:
                        while src.seq == last and not stream.stop_flag:
                            src.cond.wait(2)
                        last, jpg = src.seq, src.jpeg
                    if jpg is None:
                        continue
                    self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                                     + str(len(jpg)).encode() + b"\r\n\r\n" + jpg + b"\r\n")
            except Exception:
                pass
            finally:
                if path == "/raw":
                    stream.raw_viewers -= 1
    return Handler


class Bridge:
    def __init__(self):
        self.cfg = load_config()
        self.ffmpeg = find_ffmpeg(self.cfg.get("ffmpeg", ""))
        self.streams = {}
        self.lock = threading.Lock()
        self.mtime = 0.0
        self.quit = threading.Event()

    def start_stream(self, scfg):
        st = Stream(scfg, self.ffmpeg)
        host = self.cfg.get("host", "127.0.0.1")
        st.host = host
        try:
            st.httpd = ThreadingHTTPServer((host, int(scfg["port"])), mjpeg_handler(st))
        except OSError as e:
            log(f"[{scfg['name']}] port {scfg['port']} unavailable: {e}")
            st.status = f"port {scfg['port']} is in use"
            st.httpd = None
        if st.httpd:
            st.httpd.daemon_threads = True
            threading.Thread(target=st.httpd.serve_forever, daemon=True).start()
            st.start()
        self.streams[scfg["name"]] = st

    def apply(self, cfg):
        with self.lock:
            new = {s["name"]: s for s in cfg.get("streams", []) if s.get("enabled", True)}
            for name, st in list(self.streams.items()):
                if name not in new or int(new[name]["port"]) != int(st.cfg["port"]) or st.httpd is None:
                    st.stop()
                    del self.streams[name]
            for name, scfg in new.items():
                if name in self.streams:
                    self.streams[name].update(scfg)
                else:
                    self.start_stream(scfg)
            self.cfg = cfg

    def watch_config(self):
        while not self.quit.is_set():
            try:
                m = os.path.getmtime(CONFIG_PATH)
                if m != self.mtime:
                    self.mtime = m
                    cfg = load_config()
                    if self.streams:
                        log("settings changed, applying")
                    self.apply(cfg)
            except Exception as e:
                log(f"config error: {e!r}")
            self.quit.wait(1)

    def status(self):
        return {"running": True, "ffmpeg_found": bool(self.ffmpeg),
                "streams": [{"name": n, "port": s.cfg["port"], "status": s.status, "fps": round(s.fps, 1)}
                            for n, s in self.streams.items()]}

    def control_handler(self):
        bridge = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                if not request_allowed(self):
                    return
                path = self.path.split("?")[0]
                if path == "/status":
                    body = json.dumps(bridge.status()).encode()
                elif path == "/cameras":
                    body = json.dumps(list_cameras(max_age=0)).encode()
                elif path == "/quit":
                    # needs a custom header, which a web page can't send to another site without permission
                    if self.headers.get("X-BabbleCamBridge") != "1":
                        self.send_error(403, "forbidden")
                        return
                    body = b'{"quitting": true}'
                    bridge.quit.set()
                else:
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)
        return Handler

    def run(self):
        port = int(self.cfg.get("control_port", 8079))
        try:
            ctl = ThreadingHTTPServer(("127.0.0.1", port), self.control_handler())
        except OSError:
            log(f"already running (control port {port} is taken), not starting a second copy")
            return 1
        if not self.ffmpeg:
            log("FFmpeg not found. Run install.bat again, or set \"ffmpeg\" in config.json to the path of ffmpeg.exe")
        ctl.daemon_threads = True
        threading.Thread(target=ctl.serve_forever, daemon=True).start()
        log(f"BabbleCamBridge running, settings: {CONFIG_PATH}")
        threading.Thread(target=self.watch_config, daemon=True).start()
        self.quit.wait()
        log("stopping")
        with self.lock:
            for st in self.streams.values():
                st.stop()
        ctl.shutdown()
        return 0


if __name__ == "__main__":
    sys.exit(Bridge().run())
