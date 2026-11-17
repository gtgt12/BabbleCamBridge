"""Settings file handling. The settings live in %APPDATA%\\BabbleCamBridge\\config.json, so updating or re-downloading
the program never overwrites them."""
import copy
import json
import os

APP_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "BabbleCamBridge")
CONFIG_PATH = os.path.join(APP_DIR, "config.json")
LOG_DIR = os.path.join(APP_DIR, "logs")

DEFAULT_INPUT = {"width": 640, "height": 480, "fps": 30, "format": "mjpeg", "half_resolution": True}

DEFAULT = {
    "host": "127.0.0.1",
    "control_port": 8079,
    "ffmpeg": "",
    "streams": [
        {"name": "face", "port": 8080, "camera": None, "input": DEFAULT_INPUT, "crop": None, "mirror": False,
         "antiflicker": False, "auto_brightness": False, "smoothing": False},
        {"name": "left eye", "port": 8081, "camera": None, "input": DEFAULT_INPUT, "crop": None, "mirror": False,
         "antiflicker": True, "auto_brightness": True, "smoothing": True},
        {"name": "right eye", "port": 8082, "camera": None, "input": DEFAULT_INPUT, "crop": None, "mirror": False,
         "antiflicker": True, "auto_brightness": True, "smoothing": True},
    ],
}


def load_config():
    if not os.path.exists(CONFIG_PATH):
        save_config(DEFAULT)
    with open(CONFIG_PATH, encoding="utf-8-sig") as f:
        cfg = json.load(f)
    for s in cfg.get("streams", []):
        s.setdefault("input", copy.deepcopy(DEFAULT_INPUT))
        for k, v in DEFAULT_INPUT.items():
            s["input"].setdefault(k, v)
    return cfg


def save_config(cfg):
    os.makedirs(APP_DIR, exist_ok=True)
    tmp = CONFIG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    os.replace(tmp, CONFIG_PATH)
