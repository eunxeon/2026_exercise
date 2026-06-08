import cv2


class PoseDetector:
    """Placeholder pose detector that accepts OpenCV frames.

    This class keeps the shape expected by a future MediaPipe integration.
    For now it returns frame-derived mock landmarks so the browser-to-server
    pipeline can be tested without installing MediaPipe.
    """

    def detect_pose(self, frame):
        if frame is None:
            raise ValueError("frame is required")

        height, width = frame.shape[:2]
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        brightness = float(gray.mean())

        return {
            "frame_width": width,
            "frame_height": height,
            "brightness": brightness,
            "landmarks": {
                "shoulder": (int(width * 0.5), int(height * 0.38)),
                "elbow": (int(width * 0.55), int(height * 0.55)),
                "wrist": (int(width * 0.62), int(height * 0.72)),
            },
        }


_detector = PoseDetector()


def detect_pose(frame):
    """Detect pose data from one OpenCV frame."""
    return _detector.detect_pose(frame)
