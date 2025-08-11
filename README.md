## Project Status
**Phase 1 – Teleop + Imaging Scaffold.**  
This release provides a reliable webcam stream, manual drive controls, and scripted “snake” (boustrophedon) passes with photo capture. It’s a stable base for field data collection and future perception work.

---

## Problem Statement
Small farms need low-cost tools to scout fields for issues (weeds, pests, irrigation failures) without manual walking of every row. The goal is a simple robot workflow that can (1) traverse rows, (2) capture geo/row-context images, and (3) enable later automated analysis (object detection/segmentation).

---

## Approach & Theory of Operation
**1) Coverage Path Planning (Boustrophedon “snake”):**  
The rover drives one row forward, executes a 180° turn with a fixed radius, then drives the next row back—minimizing dead time and duplicated coverage. Parameters exposed in the UI:
- Row dwell/time (proxy for row length in mock mode)
- Turn radius & power (controls the in-place arc)
- Rows to cover

**2) Data Acquisition for Vision:**  
Photos are captured at consistent moments (start/end of row, optional end-of-every-row), with timestamped filenames. This yields a simple, ordered dataset useful for:
- Labeling weed/pest/fruit presence
- Comparing moisture/health over time (future integration with sensors/GPS)

**3) Control Abstraction (Mock-safe):**  
All motion commands go through a single function (`_send_cmd`). In **MOCK=1** they are logged and time-delayed only; in **MOCK=0** they call the Robonect mower API. This keeps the UI identical on a laptop and on the mower.

**4) Camera Backend Resilience:**  
OpenCV webcam is attempted first; if unavailable, a placeholder frame renders so the UI stays usable in demos.

---

## System Design (Phase 1)
- **Flask UI:** Live MJPEG stream, manual drive pad, mission form.
- **Mission Runner:** Threaded loop executes snake path and optional captures.
- **Storage:** Images saved to `photos/` alongside the script; filenames encode time + capture tag.
- **Config via env:** `MOCK`, `CAMERA_INDEX`, Robonect host/creds (used only when MOCK=0).

---

## Assumptions & Limits (Intentional for MVP)
- No SLAM/GPS/odometry integration in Phase 1 (time-based row traversal in mock).
- Images are unannotated; labeling/geo-tagging is planned for Phase 2.
- Motion safety interlocks are outside the scope of this UI (use in controlled areas).

---

## Roadmap (Phase 2 – Perception & Autonomy)
- **Image metadata:** Write `photos/metadata.csv` (timestamp, tag, row index, mission id).
- **Object Detection:** Train a light model (e.g., YOLOv8/RT-DETR) for weed/fruit/pest classes; add `/detect` overlay endpoint.
- **Auto-capture cadence:** Fixed interval (e.g., every N meters/seconds) and event-based triggers.
- **Navigation polish:** Closed-loop turns using compass/IMU; optional row-end detection.
- **Deployment:** One-click run on Raspberry Pi; optional Docker compose.

---

## Credits & Provenance
This app unifies two internship prototypes (movement + camera) into one tool. Portions of the movement logic were adapted from legacy mower scripts during my internship at **Central State University**. My contributions include: integrated Flask UI, mock-safe control layer, camera fallback, gallery capture, and packaging for portfolio use.

