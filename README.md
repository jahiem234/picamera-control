# Field Scout Rover (Webcam + Movement, Flask)

Single Flask app that combines **webcam live stream**, **photo capture**, and a **mock-safe movement UI** (snake path + manual drive). Works on a laptop in MOCK mode; later can talk to a Robonect-based mower when MOCK=0.

## Features
- Live MJPEG stream (OpenCV webcam; placeholder if no camera).
- Capture photos to `./photos/` with timestamps; gallery view.
- Start a snake-path "mission" (in mock it only logs).
- Manual drive buttons (mock-safe by default).

## Quickstart (Windows / laptop)
```powershell
cd field-scout-rover
python -m venv .venv
.\.venv\Scriptsctivate
pip install -r requirements.txt
$env:MOCK=1
python .\src\Picamera.py
# open http://localhost:5000
```

**Webcam not showing?**
- Close Zoom/Teams/Camera app and refresh.
- Edit `src/Picamera.py`: change `cv2.VideoCapture(0)` to `cv2.VideoCapture(1)`.
- Ensure `pillow` is installed; placeholder will render if no webcam.

## Robonect (later, on the Pi)
When you have the mower + Pi online:
```bash
export MOCK=0
export ROBONECT_BASE=http://<mower-ip>/xml
export ROBONECT_USER=GNI_Robonect
export ROBONECT_PASS=GNI
python3 src/Picamera.py
```
Now movement calls go to the mower. The UI stays the same.

## Credits & Provenance
This app unifies two internship prototypes (movement + camera) into a single web tool. Some logic was adapted from legacy mower control scripts during my internship at **Central State University**. My contributions include the integrated Flask UI, mock mode, OpenCV/placeholder camera fallback, gallery capture, and packaging for portfolio use.

## License
MIT License for my contributions. Legacy portions remain subject to their original terms, if any.
