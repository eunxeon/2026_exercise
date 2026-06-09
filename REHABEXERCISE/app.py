import base64
import traceback

import cv2
import numpy as np
from flask import Flask, jsonify, render_template, request

from pose.exercise_feedback import analyze_exercise_frame


app = Flask(__name__)


@app.route("/")
def index():
    """Render the smart mirror UI."""
    return render_template("index.html")


@app.route("/health")
def health():
    """Simple endpoint for Raspberry Pi connection checks."""
    return jsonify({"status": "ok"})


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
    """Receive one camera frame, run placeholder pose analysis, and return JSON."""
    print("[/analyze_frame] request received")

    try:
        payload = request.get_json(silent=True) or {}
        exercise_key = payload.get("exercise_key", "shoulder")
        frame_data_url = payload.get("image")

        frame = decode_data_url_frame(frame_data_url)
        print(f"[/analyze_frame] decoded frame: {frame.shape[1]}x{frame.shape[0]}")

        result = analyze_exercise_frame(frame, exercise_key=exercise_key)
        print(f"[/analyze_frame] analysis result: {result}")

        return jsonify({"success": True, **result})
    except Exception as exc:
        print(f"[/analyze_frame] error: {exc}")
        traceback.print_exc()
        return jsonify({"success": False, "error": str(exc)}), 400


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
