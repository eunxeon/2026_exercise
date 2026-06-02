"""카메라 입력을 다루기 위한 기본 구조입니다.

라즈베리파이에서는 카메라 영상만 서버로 전송하고, 서버 컴퓨터에서는 받은 영상 또는
로컬 웹캠 영상을 이 모듈로 읽어 자세 인식 모듈에 넘기는 흐름을 목표로 합니다.
"""

import cv2


class CameraStream:
    """OpenCV VideoCapture를 감싸는 간단한 카메라 스트림 클래스입니다."""

    def __init__(self, source=0):
        # source=0은 서버 컴퓨터에 연결된 기본 웹캠을 의미합니다.
        # 라즈베리파이 영상 스트림 URL을 받게 되면 source에 URL을 넣을 수 있습니다.
        self.source = source
        self.capture = None

    def start(self):
        """카메라 연결을 시작합니다."""
        self.capture = cv2.VideoCapture(self.source)
        return self.capture.isOpened()

    def read(self):
        """현재 프레임 하나를 읽습니다."""
        if self.capture is None:
            return None

        success, frame = self.capture.read()
        if not success:
            return None
        return frame

    def release(self):
        """카메라 자원을 해제합니다."""
        if self.capture is not None:
            self.capture.release()
            self.capture = None
