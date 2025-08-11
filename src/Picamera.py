#!/usr/bin/env python3
import os, io, time, math, threading
from datetime import datetime
from pathlib import Path
from flask import (
    Flask, render_template_string, request, redirect, url_for, flash,
    Response, send_from_directory, jsonify
)

# =========================
# Config
# =========================
MOCK = os.getenv("MOCK", "1") == "1"  # default mock ON for laptop safety
ROBONNECT_BASE = os.getenv("ROBONNECT_BASE", "http://192.168.4.14/xml")
ROBONECT_USER = os.getenv("ROBONECT_USER", "GNI_Robonect")
ROBONECT_PASS = os.getenv("ROBONECT_PASS", "GNI")

# Store photos next to this script (fixes 404s from mixed working dirs)
BASE_DIR = Path(__file__).resolve().parent
PHOTO_DIR = Path(os.getenv("PHOTO_DIR", BASE_DIR / "photos"))
PHOTO_DIR.mkdir(parents=True, exist_ok=True)

# Mission defaults (tweak in UI)
DEFAULT_PARAMS = {
    "ROW_TIME_MS": int(os.getenv("ROW_TIME_MS", "1500")),
    "NUM_ROWS": int(os.getenv("NUM_ROWS", "3")),
    "TURN_POWER": int(os.getenv("TURN_POWER", "60")),
    "TURN_RADIUS_CM": int(os.getenv("TURN_RADIUS_CM", "19")),
    "TURN_TIME_MS": int(os.getenv("TURN_TIME_MS", "2500")),
    "CAPTURE_EACH_ROW": os.getenv("CAPTURE_EACH_ROW", "1") == "1",
}

# Movement constants
WHEEL_BASE_CM = 35
INTER_SEGMENT_DELAY_SEC = 0.5

# =========================
# Camera backend: OpenCV webcam -> placeholder
# =========================
class CameraBackend:
    def __init__(self):
        self.backend = None
        self.cap = None
        # Allow switching camera index via env (0 default)
        cam_index = int(os.getenv("CAMERA_INDEX", "0"))
        try:
            import cv2
            self.cap = cv2.VideoCapture(cam_index)
            if self.cap is not None and self.cap.isOpened():
                self.backend = "opencv"
        except Exception:
            self.cap = None
        if self.backend is None:
            self.backend = "placeholder"

    def get_frame_jpeg(self):
        if self.backend == "opencv":
            import cv2
            ok, frame = self.cap.read()
            if not ok:
                return None
            ok, buf = cv2.imencode(".jpg", frame)
            return buf.tobytes() if ok else None
        else:
            from PIL import Image, ImageDraw
            img = Image.new("RGB", (640, 480), (245, 245, 245))
            d = ImageDraw.Draw(img)
            d.text((40, 200), "No webcam detected.\nShowing placeholder.", fill=(20, 20, 20))
            stream = io.BytesIO()
            img.save(stream, format="JPEG")
            return stream.getvalue()

    def capture_file(self, path: Path):
        frame = self.get_frame_jpeg()
        if frame:
            with open(path, "wb") as f:
                f.write(frame)
            return True
        return False

CAM = CameraBackend()

# =========================
# Movement helpers (mock-safe)
# =========================
def _send_cmd(left_power, right_power, duration_ms):
    if MOCK:
        print(f"[MOCK] direct: L={left_power} R={right_power} t={duration_ms}ms")
        time.sleep(duration_ms / 1000.0)
        return True
    import requests
    params = {
        "user": ROBONECT_USER,
        "pass": ROBONECT_PASS,
        "cmd": "direct",
        "left": str(left_power),
        "right": str(right_power),
        "timeout": str(duration_ms),
    }
    try:
        r = requests.get(ROBONNECT_BASE, params=params, timeout=5)
        r.raise_for_status()
        print(f"[HW] direct: L={left_power} R={right_power} t={duration_ms}ms")
        time.sleep(duration_ms / 1000.0)
        return True
    except Exception as e:
        print("Robonect error:", e)
        return False

def move_forward(speed, duration_ms):
    return _send_cmd(speed, speed, duration_ms)

def stop_motion():
    return _send_cmd(0, 0, 300)

def turn_with_radius_and_time(angle_deg, turn_radius_cm, total_time_ms, power=70, direction="right"):
    angle_rad = math.radians(angle_deg)
    arc_outer = angle_rad * (turn_radius_cm + WHEEL_BASE_CM / 2.0)
    arc_inner = max(1e-6, angle_rad * (turn_radius_cm - WHEEL_BASE_CM / 2.0))
    inner_power = max(0, int(power * (arc_inner / arc_outer)))
    if direction == "right":
        left_power, right_power = power, inner_power
    else:
        left_power, right_power = inner_power, power
    print(f"Turn {angle_deg} deg {direction}: L={left_power}% R={right_power}% t={total_time_ms}ms")
    return _send_cmd(left_power, right_power, total_time_ms)

# =========================
# Mission runner (snake path)
# =========================
runner_lock = threading.Lock()
runner_thread = None
runner_status = {"running": False, "message": "idle", "rows_done": 0}

def list_photos():
    return sorted([p.name for p in PHOTO_DIR.glob("*.jpg")], reverse=True)

def capture_photo(tag="shot"):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = f"{ts}_{tag}.jpg"
    path = PHOTO_DIR / name
    if CAM.capture_file(path):
        print(f"[PHOTO] saved -> {path}")
        return name
    return None

def run_snake_path(params):
    global runner_status
    runner_status = {"running": True, "message": "starting", "rows_done": 0}
    try:
        rows = params["NUM_ROWS"]
        row_ms = params["ROW_TIME_MS"]
        radius_cm = params["TURN_RADIUS_CM"]
        turn_ms = params["TURN_TIME_MS"]
        power = params["TURN_POWER"]
        capture_each = params.get("CAPTURE_EACH_ROW", True)

        direction = "right"
        print(f"[MISSION] snake: rows={rows} row_ms={row_ms} capture_each={capture_each}")
        capture_photo("start")

        for idx in range(rows):
            runner_status.update(message=f"Row {idx+1}/{rows}: forward", rows_done=idx)
            move_forward(speed=70, duration_ms=row_ms)
            time.sleep(INTER_SEGMENT_DELAY_SEC)

            if capture_each:
                capture_photo(f"row{idx+1}")

            if idx < rows - 1:
                runner_status.update(message=f"Turn {direction}", rows_done=idx)
                turn_with_radius_and_time(
                    angle_deg=180,
                    turn_radius_cm=radius_cm,
                    total_time_ms=turn_ms,
                    power=power,
                    direction=direction,
                )
                time.sleep(INTER_SEGMENT_DELAY_SEC)
                direction = "left" if direction == "right" else "right"

        stop_motion()
        capture_photo("end")
        runner_status.update(message="complete", rows_done=rows)
    except Exception as e:
        runner_status.update(message=f"error: {e}")
    finally:
        runner_status["running"] = False

def start_runner(params):
    global runner_thread
    with runner_lock:
        if runner_thread and runner_thread.is_alive():
            return False
        runner_thread = threading.Thread(target=run_snake_path, args=(params,), daemon=True)
        runner_thread.start()
        return True

# =========================
# Flask app + UI
# =========================
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET", "change_me")

PAGE = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Field Rover</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body { font-family: system-ui,-apple-system,Segoe UI,Roboto,sans-serif; margin:0; background:#f8fafc; color:#0f172a;}
    header { background:#0ea5e9; color:#fff; padding:14px 16px; display:flex; align-items:center; justify-content:space-between;}
    h1 { font-size:1.25rem; margin:0;}
    .wrap { max-width:1100px; margin:16px auto; padding: 0 16px;}
    .grid { display:grid; gap:16px; grid-template-columns: 1fr; }
    @media(min-width: 980px){ .grid{ grid-template-columns: 1.2fr 1fr; } }
    section { background:#fff; border-radius:16px; box-shadow:0 6px 24px rgba(2,8,23,.06); padding:16px; }
    label { display:block; font-size:.9rem; color:#334155; margin-top:8px;}
    input[type=number] { width:100%; padding:10px; border:1px solid #cbd5e1; border-radius:10px; font-size:1rem;}
    button { background:#0ea5e9; color:#fff; border:none; padding:10px 14px; border-radius:12px; font-size:1rem; cursor:pointer; }
    .btn-secondary { background:#64748b; }
    .status { font-size:.95rem; color:#334155; margin-top:6px;}
    .gallery { display:flex; flex-wrap:wrap; gap:8px; }
    .gallery img { width:88px; height:88px; object-fit:cover; border-radius:10px; border:1px solid #cbd5e1; cursor:pointer; }
    .badge { display:inline-block; padding:4px 8px; border-radius:999px; font-size:.8rem; background:#e2e8f0; color:#0f172a; }
    .pad { display:grid; grid-template-columns: 70px 70px 70px; gap:6px; width:max-content; }
  </style>
</head>
<body>
<header>
  <h1>Field Rover Control</h1>
  <div class="badge">MOCK: {{ 'ON' if mock else 'OFF' }}</div>
</header>
<div class="wrap">
  <div class="grid">
    <section>
      <div><b>Live Camera</b></div>
      <img id="stream" src="{{ url_for('stream') }}" style="width:100%; border-radius:14px; border:1px solid #cbd5e1;" />
      <div style="margin-top:8px; display:flex; gap:8px; flex-wrap:wrap;">
        <button onclick="capture()">Capture Photo</button>
        <form method="post" action="{{ url_for('start') }}" style="margin:0;">
          <button class="btn-secondary" type="submit">Start Mission</button>
        </form>
      </div>
      <div class="status" id="status">Status: {{ status['message'] }}</div>

      <div style="margin-top:12px;">
        <div><b>Manual Drive</b></div>
        <div class="pad">
          <div></div><button type="button" onclick="drive('fwd')">Up</button><div></div>
          <button type="button" onclick="drive('left')">Left</button>
          <button type="button" onclick="drive('stop')">Stop</button>
          <button type="button" onclick="drive('right')">Right</button>
          <div></div><button type="button" onclick="drive('back')">Down</button><div></div>
        </div>
      </div>
    </section>

    <section>
      <div><b>Mission Parameters</b></div>
      <form method="post" action="{{ url_for('start') }}">
        <label>Row Time (ms)</label>
        <input type="number" name="ROW_TIME_MS" min="500" max="20000" value="{{ params['ROW_TIME_MS'] }}" required>
        <label>Number of Rows</label>
        <input type="number" name="NUM_ROWS" min="1" max="50" value="{{ params['NUM_ROWS'] }}" required>
        <label>Turn Power (%)</label>
        <input type="number" name="TURN_POWER" min="10" max="100" value="{{ params['TURN_POWER'] }}" required>
        <label>Turn Radius (cm)</label>
        <input type="number" name="TURN_RADIUS_CM" min="10" max="200" value="{{ params['TURN_RADIUS_CM'] }}" required>
        <label>Turn Time (ms)</label>
        <input type="number" name="TURN_TIME_MS" min="500" max="12000" value="{{ params['TURN_TIME_MS'] }}" required>
        <div style="margin-top:8px;">
          <label><input type="checkbox" name="CAPTURE_EACH_ROW" value="1" {% if params['CAPTURE_EACH_ROW'] %}checked{% endif %}> Capture at each row end</label>
        </div>
        <div style="margin-top:12px;"><button type="submit">Start Mission</button></div>
      </form>
    </section>
  </div>

  <section style="margin-top:16px;">
    <div><b>Gallery</b></div>
    <div class="gallery">
      {% for p in photos %}
        <a href="{{ url_for('photo', name=p) }}" target="_blank"><img src="{{ url_for('photo', name=p) }}"></a>
      {% endfor %}
      {% if not photos %}
        <p>No photos yet.</p>
      {% endif %}
    </div>
  </section>
</div>

<script>
function capture(){
  const s = document.getElementById('status');
  s.innerText = "Capturing...";
  fetch("{{ url_for('capture') }}", { method:'POST' })
    .then(r => r.json())
    .then(j => { s.innerText = j.ok ? "Photo saved." : "Capture failed."; })
    .catch(_ => s.innerText = "Capture failed.");
}
function refreshStatus(){
  fetch("{{ url_for('status') }}")
    .then(r => r.json())
    .then(j => { document.getElementById('status').innerText = "Status: " + (j.message || "idle"); })
    .catch(_ => {});
}
setInterval(refreshStatus, 1500);

function drive(cmd){
  fetch("{{ url_for('drive') }}", {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({ cmd, power: 60, t_ms: 500 })
  }).catch(()=>{});
}
</script>
</body>
</html>
"""

@app.route("/")
def index():
    photos = list_photos()[:24]
    return render_template_string(PAGE,
                                  params=DEFAULT_PARAMS,
                                  photos=photos,
                                  status=runner_status,
                                  mock=MOCK)

@app.route("/photos/<path:name>")
def photo(name):
    return send_from_directory(str(PHOTO_DIR), name)

@app.route("/stream.mjpg")
def stream():
    def gen():
        boundary = b"--frame"
        while True:
            frame = CAM.get_frame_jpeg()
            if not frame:
                time.sleep(0.1)
                continue
            yield boundary + b"\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
    return Response(gen(), mimetype="multipart/x-mixed-replace; boundary=frame")

@app.route("/capture", methods=["POST"])
def capture():
    name = capture_photo("manual")
    if name:
        return jsonify({"ok": True, "url": url_for("photo", name=name)})
    return jsonify({"ok": False}), 500

@app.route("/start", methods=["POST"])
def start():
    # Accept overrides from form
    p = dict(DEFAULT_PARAMS)
    src = request.form or {}
    for k in ["ROW_TIME_MS","NUM_ROWS","TURN_POWER","TURN_RADIUS_CM","TURN_TIME_MS"]:
        if k in src:
            try:
                p[k] = int(src[k])
            except:
                pass
    p["CAPTURE_EACH_ROW"] = (src.get("CAPTURE_EECH_ROW") in ["1","true","True","on"]) or (src.get("CAPTURE_EACH_ROW", "0") in ["1","true","True","on"])
    ok = start_runner(p)
    if not ok:
        flash("Mission already running.", "error")
    else:
        flash("Mission started!", "ok")
    return redirect(url_for("index"))

@app.route("/status")
def status():
    return jsonify(runner_status)

# Manual drive (nudge) endpoint
def nudge(left, right, t_ms=500):
    return _send_cmd(left, right, t_ms)

@app.route("/drive", methods=["POST"])
def drive():
    data = request.get_json(silent=True) or {}
    cmd = (data.get("cmd") or "").lower()
    power = int(data.get("power", 60))
    t_ms = int(data.get("t_ms", 500))
    if cmd == "fwd":
        nudge(power, power, t_ms)
    elif cmd == "back":
        nudge(-power, -power, t_ms)
    elif cmd == "left":
        nudge(-power, power, t_ms)
    elif cmd == "right":
        nudge(power, -power, t_ms)
    elif cmd == "stop":
        stop_motion()
    return jsonify(ok=True)

if __name__ == "__main__":
    # Single combined app runs on port 5000
    app.run(host="0.0.0.0", port=5000, debug=True)
