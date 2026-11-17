# NOTE: Fully vibe coded - written by an AI (Claude). The repo owner has no programming knowledge; review before trusting.
"""Demo data for the window app (BCB_DEMO=1): made-up cameras and drawn placeholder pictures instead of real camera
images, so screenshots never show anyone's face. Nothing is saved and no server is started."""
import copy
import ctypes
import math

from PIL import Image, ImageDraw, ImageFilter, ImageGrab

from config import DEFAULT

CAMERAS = [
    {"name": "USB 2.0 Camera", "instance": "demo1", "location": "usb 1-3-4-1", "vidpid": "0c45:6366", "dshow": ""},
    {"name": "USB 2.0 Camera", "instance": "demo2", "location": "usb 1-3-4-2", "vidpid": "0c45:6366", "dshow": ""},
    {"name": "USB 2.0 Camera", "instance": "demo3", "location": "usb 1-3-4-4", "vidpid": "0c45:6366", "dshow": ""},
]

CONFIG = copy.deepcopy(DEFAULT)
CONFIG["streams"][0].update(camera={"location": "usb 1-3-4-2"}, mirror=True, crop=[90, 46, 140, 164])
CONFIG["streams"][1].update(camera={"location": "usb 1-3-4-1"}, crop=[40, 32, 240, 176])
CONFIG["streams"][2].update(camera={"location": "usb 1-3-4-4"}, crop=[40, 32, 240, 176])

STATUS = {"running": True, "streams": [{"name": s["name"], "port": s["port"], "status": "running", "fps": 25.0}
                                       for s in CONFIG["streams"]]}


def _eye(w=320, h=240):
    im = Image.new("L", (w, h), 70)
    d = ImageDraw.Draw(im)
    for y in range(h):  # soft vertical light falloff
        d.line([0, y, w, y], fill=int(60 + 50 * math.sin(math.pi * y / h)))
    cx, cy = w // 2, h // 2 + 6
    d.ellipse([cx - 95, cy - 45, cx + 95, cy + 45], fill=150)          # eye opening (skin-lit sclera)
    d.ellipse([cx - 34, cy - 34, cx + 34, cy + 34], fill=85)           # iris
    d.ellipse([cx - 15, cy - 15, cx + 15, cy + 15], fill=18)           # pupil
    d.ellipse([cx + 6, cy - 14, cx + 13, cy - 7], fill=235)            # glint
    d.arc([cx - 100, cy - 70, cx + 100, cy + 40], 200, 340, fill=40, width=6)  # upper lid / lashes
    for i in range(14):
        a = math.radians(205 + i * 9.5)
        x0, y0 = cx + 100 * math.cos(a), cy - 15 + 55 * math.sin(a)
        d.line([x0, y0, x0 + 6 * math.cos(a), y0 - 10], fill=35, width=2)
    return im.filter(ImageFilter.GaussianBlur(1.2))


def _face(w=320, h=240):
    im = Image.new("L", (w, h), 35)
    d = ImageDraw.Draw(im)
    cx = w // 2
    d.ellipse([cx - 95, 30, cx + 95, 300], fill=135)                   # lower face, lit from the headset
    d.ellipse([cx - 40, 40, cx + 40, 110], fill=160)                   # nose
    d.ellipse([cx - 22, 82, cx - 8, 96], fill=55)                      # nostrils
    d.ellipse([cx + 8, 82, cx + 22, 96], fill=55)
    d.chord([cx - 48, 140, cx + 48, 185], 0, 180, fill=95)             # lips
    d.line([cx - 46, 160, cx + 46, 160], fill=60, width=3)
    return im.filter(ImageFilter.GaussianBlur(1.5))


class FakePreview:
    def __init__(self, name):
        self.image = _face() if name == "face" else _eye()
        self.alive = True


def screenshot(root, path):
    """Save the whole window (title bar included) as a PNG, then close."""
    root.update()
    hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
    import ctypes.wintypes as wt
    rect = wt.RECT()
    try:
        ctypes.windll.dwmapi.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(rect), ctypes.sizeof(rect))  # extended frame
    except Exception:
        ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
    ImageGrab.grab(bbox=(rect.left, rect.top, rect.right, rect.bottom), all_screens=True).save(path)
    root.destroy()
