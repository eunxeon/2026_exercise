import cv2


class CameraStream:
    """Minimal OpenCV camera wrapper kept for optional server-side capture."""

    def __init__(self, camera_index=0):
        self.camera_index = camera_index
        self.capture = None

    def start(self):
        self.capture = cv2.VideoCapture(self.camera_index)
        if not self.capture.isOpened():
            raise RuntimeError("camera could not be opened")
        return self

    def read(self):
        if self.capture is None:
            raise RuntimeError("camera stream has not started")
        ok, frame = self.capture.read()
        if not ok:
            raise RuntimeError("camera frame could not be read")
        return frame

    def stop(self):
        if self.capture is not None:
            self.capture.release()
            self.capture = None
