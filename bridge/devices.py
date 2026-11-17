"""Find webcams and FFmpeg on Windows.

Identical cameras (same model, same name) can't be told apart by name, and Windows gives a camera a new
device name when it is plugged into another port. So each camera is identified by its USB location
(the chain of hub ports it hangs off), which stays the same as long as it stays in the same port."""
import glob
import json
import os
import shutil
import subprocess
import time

NOWIN = 0x08000000  # CREATE_NO_WINDOW
_VIDEO_CATEGORY = "{65e8773d-8f56-11d0-a3b9-00a0c9223196}"  # KSCATEGORY_CAPTURE

_PS_LIST = r"""
$ErrorActionPreference = 'SilentlyContinue'
$out = @()
Get-PnpDevice -PresentOnly | Where-Object { $_.Class -in 'Camera','Image' -and $_.InstanceId -like 'USB\*' } | ForEach-Object {
  $loc = (Get-PnpDeviceProperty -InstanceId $_.InstanceId -KeyName DEVPKEY_Device_LocationPaths).Data | Select-Object -First 1
  $out += [pscustomobject]@{ name = $_.FriendlyName; instance = $_.InstanceId; location = "$loc"; status = "$($_.Status)" }
}
ConvertTo-Json -InputObject @($out) -Compress
"""

_cache = {"t": 0.0, "list": []}


def _location_key(path):
    """'PCIROOT(0)#PCI(0801)#...#USBROOT(0)#USB(2)#USB(3)#USB(4)#USB(1)#USBMI(0)' -> 'usb 2-3-4-1'"""
    if "USBROOT" not in path:
        return ""
    tail = path.split("USBROOT(0)#", 1)[-1]
    ports = [p[4:-1] for p in tail.split("#") if p.startswith("USB(")]
    return "usb " + "-".join(ports) if ports else ""


def list_cameras(max_age=3.0):
    """List of dicts: name, instance, location (stable USB port key), dshow (DirectShow device name for FFmpeg),
    vidpid. Cached for a few seconds because the PowerShell query is slow."""
    if time.time() - _cache["t"] < max_age:
        return _cache["list"]
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", _PS_LIST],
                           capture_output=True, text=True, timeout=40, creationflags=NOWIN)
        raw = json.loads(r.stdout.strip() or "[]")
    except Exception:
        raw = []
    cams = []
    for d in raw if isinstance(raw, list) else [raw]:
        inst = d.get("instance") or ""
        if d.get("status") not in ("OK", "Unknown") or not inst:
            continue
        vidpid = ""
        if "VID_" in inst and "PID_" in inst:
            vidpid = (inst.split("VID_")[1][:4] + ":" + inst.split("PID_")[1][:4]).lower()
        cams.append({
            "name": d.get("name") or "Camera",
            "instance": inst,
            "location": _location_key(d.get("location") or ""),
            "vidpid": vidpid,
            "dshow": "@device_pnp_\\\\?\\" + inst.lower().replace("\\", "#") + "#" + _VIDEO_CATEGORY + "\\global",
        })
    cams.sort(key=lambda c: (c["location"], c["name"]))
    _cache["t"], _cache["list"] = time.time(), cams
    return cams


def describe(cam):
    return f'{cam["name"]}  [{cam["location"] or "no USB port"}]' + (f'  {cam["vidpid"]}' if cam["vidpid"] else "")


def find_camera(sel, cams=None):
    """sel = {"location": "usb 2-3-4-1"} (preferred) or {"name": "USB Camera", "index": 0}. Returns a camera or None."""
    if not sel:
        return None
    cams = list_cameras() if cams is None else cams
    if sel.get("location"):
        for c in cams:
            if c["location"] == sel["location"]:
                return c
        return None
    if sel.get("name"):
        same = [c for c in cams if c["name"] == sel["name"]]
        i = int(sel.get("index", 0))
        return same[i] if i < len(same) else None
    return None


def find_ffmpeg(configured=""):
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidates = [configured] if configured else []
    candidates.append(os.path.join(here, "ffmpeg", "bin", "ffmpeg.exe"))
    found = shutil.which("ffmpeg")
    if found:
        candidates.append(found)
    local = os.environ.get("LOCALAPPDATA", "")
    candidates += sorted(glob.glob(os.path.join(local, "Microsoft", "WinGet", "Packages", "*FFmpeg*", "**", "bin", "ffmpeg.exe"),
                                   recursive=True), reverse=True)
    candidates += glob.glob(os.path.join(local, "Microsoft", "WinGet", "Links", "ffmpeg.exe"))
    for c in candidates:
        # a 0-byte placeholder ffmpeg.exe exists on some systems; skip anything that small
        if c and os.path.isfile(c) and os.path.getsize(c) > 100_000:
            return c
    return None


if __name__ == "__main__":
    for c in list_cameras():
        print(describe(c))
    print("ffmpeg:", find_ffmpeg())
