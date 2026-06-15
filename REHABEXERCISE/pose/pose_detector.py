import cv2
import mediapipe as mp


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
        self._pose_landmark = mp.solutions.pose.PoseLandmark
        self._pose = mp.solutions.pose.Pose(
            static_image_mode=False,
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

        if not results.pose_landmarks:
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


_detector = PoseDetector()


def detect_pose(frame):
    """Detect pose data from one OpenCV BGR frame."""
    return _detector.detect_pose(frame)
