import base64
import logging
import os
import traceback

import cv2
import numpy as np
from flask import Flask, jsonify, render_template, request

from data_store import data_store
from pose.exercise_feedback import analyze_exercise_frame, reset_exercise


app = Flask(__name__)
app.config["JSON_AS_ASCII"] = False
if hasattr(app, "json"):
    app.json.ensure_ascii = False
DEBUG_MODE = os.getenv("DEBUG_MODE", "0").lower() in {"1", "true", "yes", "on"}
_last_analysis_state = None
MAJOR_ANALYSIS_STATES = {"STAGE_1", "STAGE_2", "STAGE_3", "COMPLETE"}

if not DEBUG_MODE:
    logging.getLogger("werkzeug").setLevel(logging.ERROR)


def debug_log(message):
    if DEBUG_MODE:
        print(message, flush=True)


@app.route("/")
def index():
    """Render the smart mirror UI."""
    return render_template("index.html")


@app.route("/health")
def health():
    """Simple endpoint for Raspberry Pi connection checks."""
    return jsonify({"status": "ok"})


@app.route("/api/devices/current")
def current_device():
    """Return the demo mirror device metadata."""
    return jsonify({"success": True, "device": data_store.get_current_device()})


@app.route("/api/devices/<device_id>/pairing-code", methods=["POST"])
def issue_pairing_code(device_id):
    """Create a server-side demo pairing code."""
    return jsonify({"success": True, **data_store.create_pairing_code(device_id)})


@app.route("/api/devices/<device_id>/pairing-status")
def pairing_status(device_id):
    """Return the current demo pairing state."""
    return jsonify({"success": True, **data_store.get_pairing_status(device_id)})


@app.route("/api/devices/<device_id>/pairing-status/demo-complete", methods=["POST"])
def demo_complete_pairing(device_id):
    """Presentation helper that marks the demo device as paired."""
    return jsonify({"success": True, **data_store.complete_pairing_for_demo(device_id)})


@app.route("/api/devices/<device_id>/users")
def device_users(device_id):
    """Return demo users for the selected mirror device."""
    return jsonify({"success": True, "device_id": device_id, "users": data_store.list_users(device_id)})


@app.route("/api/users")
def users():
    """Return users for the mirror UI."""
    return jsonify({"success": True, "users": data_store.list_users()})


@app.route("/api/exercises")
def exercises():
    """Return exercise metadata used by the mirror UI."""
    return jsonify({"success": True, "exercises": data_store.list_exercises()})


def decode_data_url_frame(frame_data_url):
    """Convert a browser canvas data URL into an OpenCV BGR frame."""
    if not frame_data_url or "," not in frame_data_url:
        raise ValueError("image data URL is missing or invalid")

    header, encoded = frame_data_url.split(",", 1)
    if "base64" not in header:
        raise ValueError("image data URL must be base64 encoded")

    image_bytes = base64.b64decode(encoded)
    image_array = np.frombuffer(image_bytes, dtype=np.uint8)
    frame = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
    if frame is None:
        raise ValueError("OpenCV could not decode the image")
    return frame


@app.route("/analyze_frame", methods=["POST"])
def analyze_frame():
    """Receive one camera frame, run pose analysis, and return JSON."""
    try:
        payload = request.get_json(silent=True) or {}
        frame_data_url = payload.get("image")

        frame = decode_data_url_frame(frame_data_url)
        debug_log(f"[/analyze_frame] decoded frame: {frame.shape[1]}x{frame.shape[0]}")

        exercise_key = payload.get("exercise_key", "shoulder")
        result = analyze_exercise_frame(frame, exercise_key=exercise_key)
        debug_log(
            "[/analyze_frame] "
            f"angle={result.get('angle')} "
            f"accuracy={result.get('accuracy')} "
            f"state={result.get('state')}"
        )

        global _last_analysis_state
        current_state = result.get("state")
        if current_state != _last_analysis_state:
            if DEBUG_MODE or current_state in MAJOR_ANALYSIS_STATES:
                print(
                    f"[analysis] state: {_last_analysis_state or 'START'} -> {current_state}",
                    flush=True,
                )
            _last_analysis_state = current_state

        return jsonify({"success": True, **result})
    except Exception as exc:
        print(f"[/analyze_frame] error: {exc}", flush=True)
        if DEBUG_MODE:
            traceback.print_exc()
        return jsonify({"success": False, "error": str(exc)}), 400


@app.route("/reset_exercise", methods=["POST"])
def reset_exercise_state():
    global _last_analysis_state
    payload = request.get_json(silent=True) or {}
    exercise_key = payload.get("exercise_key", "shoulder")
    reset_exercise(exercise_key)
    _last_analysis_state = None
    print(f"[exercise] reset: {exercise_key}", flush=True)
    return jsonify({"success": True})


if __name__ == "__main__":
    print(
        f"[server] Rehab Mirror starting on http://0.0.0.0:5000 "
        f"(debug logs: {'on' if DEBUG_MODE else 'off'})",
        flush=True,
    )
    app.run(host="0.0.0.0", port=5000, debug=DEBUG_MODE, use_reloader=DEBUG_MODE)
