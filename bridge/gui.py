# NOTE: Fully vibe coded - written by an AI (Claude). The repo owner has no programming knowledge; review before trusting.
"""BabbleCamBridge window: start/stop the camera server, pick a camera for each stream, switch the filters on/off,
and set the crop by dragging the box on the live picture. Closing the window leaves the server running."""
import copy
import io
import json
import os
import subprocess
import sys
import threading
import time
import tkinter as tk
import urllib.request
from tkinter import messagebox, ttk

from PIL import Image, ImageTk

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from config import APP_DIR, CONFIG_PATH, DEFAULT_INPUT, load_config, save_config  # noqa: E402
from devices import NOWIN, describe, list_cameras  # noqa: E402

PREVIEW_W = 320
STARTUP_LNK = os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs\Startup",
                           "BabbleCamBridge.lnk")


def pythonw():
    exe = sys.executable
    w = os.path.join(os.path.dirname(exe), "pythonw.exe")
    return w if os.path.exists(w) else exe


def http_json(url, timeout=1.5):
    req = urllib.request.Request(url, headers={"X-BabbleCamBridge": "1"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


class Preview(threading.Thread):
    """Reads the /raw MJPEG stream of one port and keeps the newest picture."""

    def __init__(self, port):
        super().__init__(daemon=True)
        self.port = port
        self.image = None
        self.alive = True

    def run(self):
        while self.alive:
            try:
                r = urllib.request.urlopen(f"http://127.0.0.1:{self.port}/raw", timeout=4)
                buf = b""
                while self.alive:
                    chunk = r.read(16384)
                    if not chunk:
                        break
                    buf += chunk
                    while True:
                        a = buf.find(b"\xff\xd8")
                        b = buf.find(b"\xff\xd9", a + 2) if a >= 0 else -1
                        if a < 0 or b < 0:
                            break
                        self.image = Image.open(io.BytesIO(buf[a:b + 2])).convert("L")
                        buf = buf[b + 2:]
                    if len(buf) > 2_000_000:
                        buf = b""
                r.close()
            except Exception:
                self.image = None
                time.sleep(1.5)


class StreamPanel(ttk.LabelFrame):
    def __init__(self, app, parent, idx):
        self.app, self.idx = app, idx
        s = app.cfg["streams"][idx]
        super().__init__(parent, text=f'  {s["name"]}  ', padding=8)
        self.preview = None
        self.photo = None
        self.drag = None

        top = ttk.Frame(self)
        top.pack(fill="x")
        ttk.Label(top, text="Port").pack(side="left")
        self.port = tk.StringVar(value=str(s["port"]))
        e = ttk.Entry(top, textvariable=self.port, width=6)
        e.pack(side="left", padx=(4, 10))
        e.bind("<FocusOut>", lambda ev: self.changed())
        e.bind("<Return>", lambda ev: self.changed())
        self.url = ttk.Label(top, foreground="#4a8")
        self.url.pack(side="left")
        self.state = ttk.Label(top, foreground="#888")
        self.state.pack(side="right")

        row = ttk.Frame(self)
        row.pack(fill="x", pady=(6, 0))
        ttk.Label(row, text="Camera").pack(side="left")
        self.camera = ttk.Combobox(row, state="readonly", width=46)
        self.camera.pack(side="left", padx=4, fill="x", expand=True)
        self.camera.bind("<<ComboboxSelected>>", lambda ev: self.changed())

        opts = ttk.Frame(self)
        opts.pack(fill="x", pady=(6, 0))
        self.flags = {}
        for key, label in (("mirror", "Mirror"), ("antiflicker", "Anti-flicker"),
                           ("auto_brightness", "Auto brightness"), ("smoothing", "Noise smoothing")):
            v = tk.BooleanVar(value=bool(s.get(key)))
            ttk.Checkbutton(opts, text=label, variable=v, command=self.changed).pack(side="left", padx=(0, 10))
            self.flags[key] = v

        self.canvas = tk.Canvas(self, width=PREVIEW_W, height=240, bg="#000", highlightthickness=0, cursor="fleur")
        self.canvas.pack(pady=(8, 2))
        self.canvas.bind("<ButtonPress-1>", self.press)
        self.canvas.bind("<B1-Motion>", self.motion)
        self.canvas.bind("<ButtonRelease-1>", self.release)
        self.canvas.bind("<MouseWheel>", self.wheel)

        bottom = ttk.Frame(self)
        bottom.pack(fill="x")
        self.crop_label = ttk.Label(bottom, foreground="#888")
        self.crop_label.pack(side="left")
        ttk.Button(bottom, text="Whole picture", command=self.crop_full).pack(side="right")
        ttk.Label(self, text="Drag the red box to move it, drag its corner or use the mouse wheel to resize.",
                  foreground="#888").pack(anchor="w")
        self.refresh_cameras()
        self.start_preview()

    @property
    def s(self):
        return self.app.cfg["streams"][self.idx]

    # -- cameras ----------------------------------------------------------------------------------
    def refresh_cameras(self):
        cams = self.app.cameras
        self.cam_list = [None] + cams
        self.camera["values"] = ["(no camera)"] + [describe(c) for c in cams]
        sel = self.s.get("camera") or {}
        pick = 0
        for i, c in enumerate(cams, 1):
            if (sel.get("location") and c["location"] == sel["location"]) or \
               (not sel.get("location") and sel.get("name") == c["name"]):
                pick = i
                break
        if sel and pick == 0:
            self.camera["values"] = list(self.camera["values"]) + [f'(not plugged in: {sel.get("location") or sel.get("name")})']
            pick = len(self.camera["values"]) - 1
        self.camera.current(pick)

    def selected_camera(self):
        i = self.camera.current()
        if 0 < i < len(self.cam_list):
            c = self.cam_list[i]
            if c["location"]:
                return {"location": c["location"], "name": c["name"]}
            same = [x for x in self.app.cameras if x["name"] == c["name"]]
            return {"name": c["name"], "index": same.index(c)}
        if i >= len(self.cam_list):
            return self.s.get("camera")  # keep the unplugged one
        return None

    # -- settings ---------------------------------------------------------------------------------
    def changed(self):
        s = self.s
        try:
            port = int(self.port.get())
            if not 1024 <= port <= 65535:
                raise ValueError
        except ValueError:
            messagebox.showerror("BabbleCamBridge", "The port must be a number between 1024 and 65535.")
            self.port.set(str(s["port"]))
            return
        if port != s["port"]:
            s["port"] = port
            self.start_preview()
        s["camera"] = self.selected_camera()
        for k, v in self.flags.items():
            s[k] = bool(v.get())
        self.app.save_soon()

    def start_preview(self):
        if self.preview:
            self.preview.alive = False
        self.preview = Preview(self.s["port"])
        self.preview.start()

    # -- crop box on the preview ------------------------------------------------------------------
    def frame_size(self):
        img = self.preview.image if self.preview else None
        if img:
            return img.size
        inp = self.s.get("input", DEFAULT_INPUT)
        half = inp.get("half_resolution", True)
        return (inp["width"] // 2, inp["height"] // 2) if half else (inp["width"], inp["height"])

    def crop(self):
        w, h = self.frame_size()
        c = self.s.get("crop")
        return [0, 0, w, h] if not c else [int(v) for v in c]

    def scale(self):
        w, _ = self.frame_size()
        return PREVIEW_W / w

    def press(self, ev):
        k = self.scale()
        x, y, w, h = self.crop()
        cx, cy = ev.x / k, ev.y / k
        corner = abs(cx - (x + w)) < 14 / k and abs(cy - (y + h)) < 14 / k
        self.drag = ("resize" if corner else "move", cx, cy, [x, y, w, h])

    def motion(self, ev):
        if not self.drag:
            return
        mode, sx, sy, (x, y, w, h) = self.drag
        k = self.scale()
        dx, dy = ev.x / k - sx, ev.y / k - sy
        fw, fh = self.frame_size()
        if mode == "move":
            x = int(min(max(0, x + dx), fw - w))
            y = int(min(max(0, y + dy), fh - h))
        else:
            w = int(min(max(16, w + dx), fw - x))
            h = int(min(max(16, h + dy), fh - y))
        self.s["crop"] = [x, y, w - w % 2, h - h % 2]

    def release(self, ev):
        if self.drag:
            self.drag = None
            self.app.save_soon()

    def wheel(self, ev):
        x, y, w, h = self.crop()
        fw, fh = self.frame_size()
        f = 0.95 if ev.delta > 0 else 1.05
        nw, nh = int(min(max(16, w * f), fw)), int(min(max(16, h * f), fh))
        nx = int(min(max(0, x + (w - nw) / 2), fw - nw))
        ny = int(min(max(0, y + (h - nh) / 2), fh - nh))
        self.s["crop"] = [nx, ny, nw - nw % 2, nh - nh % 2]
        self.app.save_soon()

    def crop_full(self):
        self.s["crop"] = None
        self.app.save_soon()

    # -- drawing ----------------------------------------------------------------------------------
    def draw(self, st):
        self.url.config(text=f'http://127.0.0.1:{self.s["port"]}/')
        if st:
            fps = f'  {st["fps"]:.0f} fps' if st.get("fps") else ""
            self.state.config(text=f'{st["status"]}{fps}', foreground="#4a8" if st["status"] == "running" else "#c84")
        else:
            self.state.config(text="server stopped", foreground="#888")
        img = self.preview.image if self.preview else None
        cv = self.canvas
        cv.delete("all")
        w, h = self.frame_size()
        k = self.scale()
        ch = int(h * k)
        if int(cv["height"]) != ch:
            cv.config(height=ch)
        if img:
            self.photo = ImageTk.PhotoImage(img.resize((PREVIEW_W, ch)))
            cv.create_image(0, 0, image=self.photo, anchor="nw")
        else:
            cv.create_text(PREVIEW_W // 2, ch // 2, text="no picture", fill="#666")
        x, y, cw, chh = self.crop()
        cv.create_rectangle(x * k, y * k, (x + cw) * k, (y + chh) * k, outline="#f44", width=2)
        cv.create_line((x + cw / 2) * k, y * k, (x + cw / 2) * k, (y + chh) * k, fill="#6f6")
        cv.create_line(x * k, (y + chh / 2) * k, (x + cw) * k, (y + chh / 2) * k, fill="#6f6")
        cv.create_rectangle((x + cw) * k - 7, (y + chh) * k - 7, (x + cw) * k, (y + chh) * k, fill="#f44", outline="")
        self.crop_label.config(text=f"crop {cw}x{chh} at {x},{y} of {w}x{h}")


class App:
    def __init__(self, root):
        self.root = root
        root.title("BabbleCamBridge")
        self.cfg = load_config()
        self.cameras = list_cameras(max_age=0)
        self.status = None
        self.save_job = None

        bar = ttk.Frame(root, padding=8)
        bar.pack(fill="x")
        self.server_label = ttk.Label(bar, text="checking server...", font=("Segoe UI", 11, "bold"))
        self.server_label.pack(side="left")
        ttk.Button(bar, text="Stop", command=self.stop_server).pack(side="right")
        ttk.Button(bar, text="Start / Restart", command=self.restart_server).pack(side="right", padx=4)
        ttk.Button(bar, text="Refresh camera list", command=self.refresh_cameras).pack(side="right", padx=4)

        self.panels_frame = ttk.Frame(root, padding=(8, 0))
        self.panels_frame.pack(fill="both", expand=True)
        self.panels = []
        for i in range(len(self.cfg["streams"])):
            p = StreamPanel(self, self.panels_frame, i)
            p.grid(row=0, column=i, padx=4, pady=4, sticky="n")
            self.panels.append(p)

        foot = ttk.Frame(root, padding=8)
        foot.pack(fill="x")
        self.autostart = tk.BooleanVar(value=os.path.exists(STARTUP_LNK))
        ttk.Checkbutton(foot, text="Start the cameras automatically when Windows starts", variable=self.autostart,
                        command=self.toggle_autostart).pack(side="left")
        ttk.Button(foot, text="Open settings folder", command=lambda: os.startfile(APP_DIR)).pack(side="right")
        ttk.Label(root, text="Closing this window keeps the cameras running in the background. "
                             "In Babble, use the addresses shown above. Babble does not reconnect by itself: "
                             "restart Babble after restarting the server.  (Fully vibe coded by an AI - use at your own risk.)",
                  foreground="#888", padding=(8, 0, 8, 8), wraplength=1000).pack(anchor="w")

        if not self.server_up():
            self.start_server()
        self.tick()
        self.poll_status()

    # -- server control ---------------------------------------------------------------------------
    @property
    def control(self):
        return f'http://127.0.0.1:{int(self.cfg.get("control_port", 8079))}'

    def server_up(self):
        try:
            http_json(self.control + "/status", 0.8)
            return True
        except Exception:
            return False

    def start_server(self):
        subprocess.Popen([pythonw(), os.path.join(HERE, "server.py")], cwd=HERE,
                         creationflags=NOWIN | 0x00000008)  # DETACHED_PROCESS

    def stop_server(self):
        try:
            http_json(self.control + "/quit", 2)
        except Exception:
            pass

    def restart_server(self):
        self.flush_save()
        self.stop_server()
        for _ in range(30):
            if not self.server_up():
                break
            time.sleep(0.2)
        time.sleep(0.5)
        self.start_server()

    def poll_status(self):
        def work():
            try:
                self.status = http_json(self.control + "/status")
            except Exception:
                self.status = None
            self.root.after(1000, self.poll_status)
        threading.Thread(target=work, daemon=True).start()

    # -- settings ---------------------------------------------------------------------------------
    def save_soon(self):
        if self.save_job:
            self.root.after_cancel(self.save_job)
        self.save_job = self.root.after(400, self.flush_save)

    def flush_save(self):
        self.save_job = None
        save_config(self.cfg)

    def refresh_cameras(self):
        self.cameras = list_cameras(max_age=0)
        for p in self.panels:
            p.refresh_cameras()

    def toggle_autostart(self):
        if self.autostart.get():
            ps = ("$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:LNK);"
                  "$s.TargetPath=$env:EXE;$s.Arguments='\"'+$env:SRV+'\"';$s.WorkingDirectory=$env:DIR;$s.Save()")
            env = dict(os.environ, LNK=STARTUP_LNK, EXE=pythonw(), SRV=os.path.join(HERE, "server.py"), DIR=HERE)
            subprocess.run(["powershell", "-NoProfile", "-Command", ps], env=env, creationflags=NOWIN)
        elif os.path.exists(STARTUP_LNK):
            os.remove(STARTUP_LNK)

    # -- redraw loop ------------------------------------------------------------------------------
    def tick(self):
        st = self.status
        if st:
            self.server_label.config(text="Server running", foreground="#2a7")
        else:
            self.server_label.config(text="Server stopped", foreground="#c44")
        by_name = {x["name"]: x for x in (st or {}).get("streams", [])}
        for p in self.panels:
            p.draw(by_name.get(p.s["name"]))
        self.root.after(80, self.tick)


def main():
    root = tk.Tk()
    apply_dark_theme(root)
    App(root)
    root.mainloop()


BG, PANEL, FIELD, FG, BORDER, ACCENT = "#1e1f22", "#2b2d31", "#383a40", "#e3e5e8", "#4e5058", "#5865f2"


def apply_dark_theme(root):
    """Dark window everywhere (easy on the eyes), including the Windows title bar."""
    root.configure(bg=BG)
    st = ttk.Style(root)
    try:
        st.theme_use("clam")  # the only built-in theme whose colors can be fully changed
    except tk.TclError:
        pass
    st.configure(".", background=BG, foreground=FG, fieldbackground=FIELD, bordercolor=BORDER,
                 lightcolor=PANEL, darkcolor=PANEL, troughcolor=PANEL, focuscolor=ACCENT,
                 selectbackground=ACCENT, selectforeground=FG, insertcolor=FG)
    st.configure("TFrame", background=BG)
    st.configure("TLabel", background=BG, foreground=FG)
    st.configure("TLabelframe", background=BG, bordercolor=BORDER)
    st.configure("TLabelframe.Label", background=BG, foreground=FG)
    st.configure("TButton", background=PANEL, foreground=FG, bordercolor=BORDER, padding=(10, 4))
    st.map("TButton", background=[("active", FIELD), ("pressed", BORDER)])
    st.configure("TCheckbutton", background=BG, foreground=FG, indicatorbackground=FIELD, indicatorforeground=FG)
    st.map("TCheckbutton", background=[("active", BG)], indicatorbackground=[("selected", ACCENT), ("active", BORDER)])
    st.configure("TEntry", fieldbackground=FIELD, foreground=FG, insertcolor=FG)
    st.configure("TCombobox", fieldbackground=FIELD, background=PANEL, foreground=FG, arrowcolor=FG)
    st.map("TCombobox", fieldbackground=[("readonly", FIELD)], foreground=[("readonly", FG)],
           selectbackground=[("readonly", FIELD)], selectforeground=[("readonly", FG)])
    # the drop-down list of a combobox is a classic Tk listbox
    root.option_add("*TCombobox*Listbox.background", FIELD)
    root.option_add("*TCombobox*Listbox.foreground", FG)
    root.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
    root.option_add("*TCombobox*Listbox.selectForeground", FG)
    # dark Windows title bar (Windows 10 2004+ / 11); ignored elsewhere
    try:
        import ctypes
        root.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
        on = ctypes.c_int(1)
        for attr in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE (new / old id)
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(on), ctypes.sizeof(on)) == 0:
                break
    except Exception:
        pass


if __name__ == "__main__":
    main()
