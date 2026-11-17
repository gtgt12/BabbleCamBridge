> [!CAUTION]
> # 🛑 DISABLE THE IR LIGHT NOW BEFORE YOU USE EYE TRACKING
> ## Disable the IR LEDs on the camera boards first.
> **The infrared LEDs on these cheap camera boards were never designed or tested for shining into your eyes. Their light output is unknown and can be unsafe.**
> **Only use these cameras for eye tracking with the LEDs fully disabled** (desoldered, removed, or completely covered). **No IR light from the board.** Your eyes are not worth the risk.
> If your eyes feel strained, hurt or tired after using eye tracking, stop and see an eye doctor.
>
> **💡 How it works without the LEDs:** turn the **display brightness up inside your headset**. The light from the lenses lights up your eyes, and BabbleCamBridge's **auto brightness** handles the rest. (In very dark VR worlds the eye picture gets darker and noisier, so tracking can be a bit worse there. This only works **without a visible-light-blocking / IR-pass filter** in front of the camera, because those filters block the display light.)

# BabbleCamBridge

> ⚠️ **Fully vibe coded.** This whole project was written by an AI (Claude) while I described what I wanted. **I have zero programming knowledge** and can't review or fix the code myself. It works on my PC, but use it at your own risk, and please check the code yourself or ask someone who can before trusting it.

Run **three USB eye/face tracking cameras at the same time** for [Baballonia / Project Babble](https://github.com/Project-Babble/Baballonia) on Windows, even through one cheap USB 2.0 hub (for example in the Valve Index frunk). Works with VRCFaceTracking (VRCFT) and VRChat eye tracking / face tracking setups that use cheap DIY IR cameras.

## Tested hardware

| Part | What was used |
|---|---|
| Eye cameras (×2) + face/mouth camera (×1) | **HBVCAM-1914S** IR camera module, **GC0308** sensor, shows up as **"USB 2.0 Camera" / "USB Camera"** by Sonix, USB ID **VID_0C45 PID_6366** (`0c45:6366`), 640×480 MJPEG |
| USB hub | cheap (~5 €) USB 3.x hub with **3× USB 2.0 + 1× USB 3.0** ports, plugged into the **Valve Index frunk** USB port (no Raspberry Pi needed) |
| Headset | Valve Index at 90 Hz |
| Software | Baballonia (Project Babble) 1.1.1.x, Windows 11 |

Other cheap UVC webcams with MJPEG (e.g. other Sonix / GC0308 / OV2640 / OV7725 based IR cameras) should work the same way. If you test another camera, please open an issue so it can be added here.

## Symptoms this fixes

If you search for any of these, you're in the right place:

- Babble / Baballonia: **third camera won't connect**, only 2 of 3 cameras work, "**No data was received ... on any backend**", "**Maybe the camera is opened somewhere else?**"
- 3 USB cameras on one USB hub: **"not enough USB bandwidth"**, camera works only 1 in 10 tries, needs unplugging and replugging
- Workaround with **OBS + virtual camera** needed to get all eye cameras into Babble
- **Flickering eye cameras** / rolling bands / stripes in the eye picture caused by the **VR headset display** (Valve Index 90 Hz, low persistence)
- Eye picture **too dark in dark VR worlds and too bright in bright worlds**
- Identical cameras (same name) **swap places** after replugging or reboot

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
- Window app with live previews (dark mode), or run it **in the background** with no window
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
