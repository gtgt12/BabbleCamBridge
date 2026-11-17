# BabbleCamBridge

Run **three USB eye/face tracking cameras at the same time** for [Baballonia / Project Babble](https://github.com/Project-Babble/Baballonia) on Windows, even through one cheap USB 2.0 hub (for example in the Valve Index frunk).

## The problem it fixes

Most apps open webcams **uncompressed**. Three uncompressed 640×480 cameras need more bandwidth than USB 2.0 can reserve, so the third camera fails to open ("won't connect", only works 1 in 10 tries, needs OBS + virtual camera...).

BabbleCamBridge always asks the cameras for **compressed MJPEG**, which is only a few Mbit/s each, so all of them fit. It then serves each camera as a local video stream that Babble reads like an IP camera.

## Features

- 3 (or more) cameras at once, each on its own address, e.g. `http://127.0.0.1:8080/`
- Identical cameras are told apart by **which USB port** they are plugged into, so the assignment survives replugging and reboots (as long as each camera stays in its port)
- **Crop** each picture by dragging a box on the live preview
- **Anti-flicker** for eye cameras: removes the rolling bands a VR headset display (e.g. Valve Index at 90 Hz) causes in cheap IR cameras
- **Auto brightness**: eyes keep the same brightness in dark and bright VR worlds
- Optional mirror and noise smoothing
- Window app with live previews, or run it **in the background** with no window
- Optional autostart with Windows
- Auto-reconnect: if a camera drops out, it comes back by itself

## Install

1. Download this project (green **Code** button → **Download ZIP**) and unzip it somewhere permanent, e.g. `C:\BabbleCamBridge`.
2. Double-click **`install.bat`**. It installs Python 3.12 and FFmpeg if you don't have them (via winget), sets everything up, and puts two shortcuts on your desktop.
3. Open **BabbleCamBridge** from the desktop.

## Setup

1. In the window, pick a **camera** for each stream (face, left eye, right eye). The list shows each camera with its USB port, e.g. `USB Camera [usb 2-3-4-1]`. Use the live preview to see which one is which.
2. Drag the **red box** over the part Babble should see (mouse wheel or the box corner to resize). Use **Whole picture** to reset.
3. Tick **Anti-flicker** / **Auto brightness** for the eye cameras if you see flicker or brightness changes.
4. In **Babble**, enter the addresses shown in the window as the camera for face / left eye / right eye, e.g. `http://127.0.0.1:8080/`.

Settings are saved automatically and apply live. They are stored in `%APPDATA%\BabbleCamBridge\config.json`, so updating the program keeps them.

**Important:** Babble does not reconnect to a stream by itself. If you restart the server (or it wasn't running when Babble started), restart Babble.

If you change auto brightness or the crop a lot, recalibrate your eyes in Babble, because the pictures look different.

## Run in the background

- **BabbleCamBridge (background)** on the desktop (or `start-background.bat`) starts the server with no window.
- `stop.bat` stops it.
- In the window, tick **Start the cameras automatically when Windows starts** to autostart.
- Closing the window keeps the server running.

## Addresses

| Address | What |
|---|---|
| `http://127.0.0.1:<port>/` | cropped, processed stream (for Babble) |
| `http://127.0.0.1:<port>/raw` | whole picture (for aiming the camera) |
| `http://127.0.0.1:<port>/snapshot.jpg` | one picture |
| `http://127.0.0.1:8079/status` | status of all streams (JSON) |

## Troubleshooting

- **"waiting for camera"**: the camera isn't plugged into the port you picked. Click *Refresh camera list* and pick it again.
- **"port is in use"**: another program uses that port (an old camera server, OBS...). Close it or choose another port.
- **No picture at all**: check `%APPDATA%\BabbleCamBridge\logs` for errors. Make sure no other program (OBS, Babble set to a USB camera directly) has the camera open.
- **Anti-flicker** assumes the camera runs at 25 fps and the headset at 90 Hz (pattern repeats every 5 frames). For other combinations set `antiflicker_period` in `config.json`.

## Requirements

Windows 10/11, MJPEG-capable USB cameras (most cheap UVC cameras), Python 3.10+ and FFmpeg (installed automatically).

## License

MIT
