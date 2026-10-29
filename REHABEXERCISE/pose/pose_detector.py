import logging
import math
import time
from threading import RLock
from pose.person_tracking import PersonTracker, crop_box

import cv2


TRACKED_LANDMARKS = {
    "NOSE",
    "LEFT_EYE",
    "RIGHT_EYE",
    "LEFT_SHOULDER",
    "LEFT_ELBOW",
    "LEFT_WRIST",
    "RIGHT_SHOULDER",
    "RIGHT_ELBOW",
    "RIGHT_WRIST",
    "LEFT_HIP",
    "RIGHT_HIP",
}

VISIBILITY_LANDMARKS = TRACKED_LANDMARKS - {"NOSE", "LEFT_EYE", "RIGHT_EYE"}

MIN_VISIBILITY = 0.5


class PoseDetector:
    """Detect human pose landmarks from OpenCV BGR frames using MediaPipe."""

    def __init__(self):
        import mediapipe as mp
        self._pose_landmark = mp.solutions.pose.PoseLandmark
        self._pose = mp.solutions.pose.Pose(
            static_image_mode=True,
            model_complexity=1,
            enable_segmentation=False,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )

    def detect_pose(self, frame):
        if frame is None:
            raise ValueError("frame is required")

        height, width = frame.shape[:2]
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        rgb_frame.flags.writeable = False
        results = self._pose.process(rgb_frame)

        if not results.pose_landmarks or not results.pose_world_landmarks:
            return {
                "state": "NO_PERSON",
                "frame_width": width,
                "frame_height": height,
                "landmarks": None,
            }

        landmarks = {}
        low_visibility = False

        world_landmarks = results.pose_world_landmarks.landmark

        for name in TRACKED_LANDMARKS:
            landmark = results.pose_landmarks.landmark[self._pose_landmark[name].value]
            world_landmark = world_landmarks[self._pose_landmark[name].value]
            visibility = float(landmark.visibility)
            if name in VISIBILITY_LANDMARKS and visibility < MIN_VISIBILITY:
                low_visibility = True

            landmarks[name] = {
                "x": float(landmark.x),
                "y": float(landmark.y),
                "z": float(landmark.z),
                "visibility": visibility,
                "pixel": (int(landmark.x * width), int(landmark.y * height)),
                "normalized": (float(landmark.x), float(landmark.y), float(landmark.z)),
                "world": (
                    float(world_landmark.x),
                    float(world_landmark.y),
                    float(world_landmark.z),
                ),
            }

        return {
            "state": "LOW_VISIBILITY" if low_visibility else "TRACKING",
            "frame_width": width,
            "frame_height": height,
            "landmarks": landmarks,
        }


# Flask serializes analysis/reset as well; this protects direct legacy callers.
analysis_lock = RLock()
_detector = None
_person_tracker = PersonTracker()
_previous = None
_previous_time = None
_good_frames = 0
_last_crop = None


def reset_pose_tracking():
    global _previous, _previous_time, _good_frames, _last_crop, _detector
    with analysis_lock:
        _person_tracker.reset()
        _previous, _previous_time, _last_crop = None, None, None
        _good_frames = 0
        if _detector is not None:
            _detector._pose.close()
            _detector = None


def _paused(state, width, height, tracking):
    global _good_frames, _last_crop
    _good_frames = 0
    _last_crop = None
    return {"state": state, "frame_width": width, "frame_height": height,
            "landmarks": None, "tracking": tracking, "analysis_valid": False}


def detect_pose(frame):
    """Keep the legacy signature; only the locked person's crop reaches MediaPipe."""
    global _detector, _previous, _previous_time, _good_frames, _last_crop
    if frame is None:
        raise ValueError("frame is required")
    with analysis_lock:
        h, w = frame.shape[:2]
        tracking = {}
        try:
            state, box, coverage, tracks = _person_tracker.detect(frame)
        except Exception as exc:
            if getattr(_person_tracker, "last_error", None) != str(exc):
                logging.getLogger(__name__).exception("Person tracking failed")
            _person_tracker.last_error = str(exc)
            # No whole-frame fallback, and no automatic reselection after failure.
            if _person_tracker.lock.target_id is not None:
                _person_tracker.lock.requires_confirmation = True
            return _paused("TRACKING_ERROR", w, h, {"requires_confirmation": _person_tracker.lock.requires_confirmation})
        _person_tracker.last_error = None
        tracking = {"target_id": _person_tracker.lock.target_id,
                    "target_box": list(box) if box else None, "overlap": coverage,
                    "roi": [.25 * w, .1 * h, .75 * w, .95 * h],
                    "people": [{"id": tid, "box": list(b)} for tid, b, _ in tracks],
                    "requires_confirmation": _person_tracker.lock.requires_confirmation}
        if state != "TRACKING":
            return _paused(state, w, h, tracking)
        x1, y1, x2, y2 = crop_box(box, w, h)
        crop = (x1, y1, x2, y2)
        # Crop coordinates change between frames. Independent image inference
        # prevents MediaPipe from propagating a bystander's cached skeleton.
        if _detector is None:
            _detector = PoseDetector()
        _last_crop = crop
        pose = _detector.detect_pose(frame[y1:y2, x1:x2])
        if pose["state"] != "TRACKING":
            return _paused(pose["state"], w, h, tracking)
        landmarks = pose["landmarks"]
        if coverage > .1 and any(landmarks[n]["visibility"] < .7 for n in VISIBILITY_LANDMARKS):
            return _paused("LOW_VISIBILITY", w, h, tracking)
        for point in landmarks.values():
            point["x"] = (point["x"] * (x2 - x1) + x1) / w
            point["y"] = (point["y"] * (y2 - y1) + y1) / h
            point["z"] *= (x2 - x1) / w
            point["normalized"] = (point["x"], point["y"], point["z"])
            point["pixel"] = (int(point["x"] * w), int(point["y"] * h))
            # world remains MediaPipe's metric 3D output; never scale by crop pixels.
        now = time.monotonic()
        torso = [landmarks[n]["pixel"] for n in ("LEFT_SHOULDER", "RIGHT_SHOULDER", "LEFT_HIP", "RIGHT_HIP")]
        if any(not (box[0] <= p[0] <= box[2] and box[1] <= p[1] <= box[3]) for p in torso):
            return _paused("LOW_CONFIDENCE", w, h, tracking)
        # Reject a skeleton whose torso also belongs to another person's box.
        for tid, other, _ in tracks:
            if tid != tracking["target_id"] and sum(other[0] <= p[0] <= other[2] and other[1] <= p[1] <= other[3] for p in torso) >= 3:
                return _paused("OCCLUDED", w, h, tracking)
        points = {n: tuple(landmarks[n]["pixel"]) for n in VISIBILITY_LANDMARKS}
        scale = max(1, math.hypot(box[2] - box[0], box[3] - box[1]))
        if _previous is not None:
            dt = min(.8, max(.01, now - _previous_time))
            # Generous wrists/elbows allowance; torso motion uses a tighter bound.
            bad = any(math.dist(points[n], _previous[n]) / scale >
                      min(.75, (.12 if "HIP" in n or "SHOULDER" in n else .22) + dt * (1 if "HIP" in n or "SHOULDER" in n else 2))
                      for n in points)
            if bad:
                return _paused("LOW_CONFIDENCE", w, h, tracking)
        if not all(math.isfinite(v) for p in landmarks.values() for v in (*p["normalized"], *p["world"])):
            return _paused("LOW_CONFIDENCE", w, h, tracking)
        _previous, _previous_time = points, now
        _good_frames += 1
        if _good_frames < 2:
            return {"state": "STABILIZING", "frame_width": w, "frame_height": h,
                    "landmarks": None, "tracking": tracking, "analysis_valid": False}
        return {"state": "TRACKING", "frame_width": w, "frame_height": h,
                "landmarks": landmarks, "tracking": tracking, "analysis_valid": True}
