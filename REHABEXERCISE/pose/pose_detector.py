"""MediaPipe 자세 인식 모듈의 기본 구조입니다.

현재 단계에서는 실제 MediaPipe 실행 대신 placeholder 데이터를 반환합니다.
나중에 서버에서 카메라 프레임을 받은 뒤 detect_pose(frame)을 호출하도록 연결하면 됩니다.
"""


class PoseDetector:
    """프레임에서 관절 좌표를 추출하는 역할을 담당합니다."""

    def __init__(self):
        # TODO: MediaPipe Pose 객체를 이곳에서 초기화합니다.
        self.is_ready = True

    def detect_pose(self, frame):
        """카메라 프레임을 받아 관절 좌표를 반환합니다.

        Args:
            frame: OpenCV 형식의 이미지 프레임입니다.

        Returns:
            dict: 관절 이름을 key로 하고 x, y, visibility 값을 담은 좌표 정보입니다.
        """
        # frame은 아직 사용하지 않습니다. 실제 구현 시 MediaPipe 입력으로 전달합니다.
        _ = frame

        return {
            "left_shoulder": {"x": 0.42, "y": 0.34, "visibility": 1.0},
            "left_elbow": {"x": 0.34, "y": 0.44, "visibility": 1.0},
            "left_wrist": {"x": 0.30, "y": 0.56, "visibility": 1.0},
            "right_shoulder": {"x": 0.58, "y": 0.34, "visibility": 1.0},
            "right_elbow": {"x": 0.66, "y": 0.44, "visibility": 1.0},
            "right_wrist": {"x": 0.70, "y": 0.56, "visibility": 1.0},
        }


def detect_pose(frame):
    """간단히 함수 형태로도 사용할 수 있도록 제공하는 helper입니다."""
    detector = PoseDetector()
    return detector.detect_pose(frame)
