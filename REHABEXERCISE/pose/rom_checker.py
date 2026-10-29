import time

import numpy as np

from pose.pose_detector import detect_pose
from pose.analysis_states import INVALID_EXERCISE_ANALYSIS_STATES, UNAVAILABLE_EXERCISE_FEEDBACK


ROM_NORMAL_THRESHOLD_DEG = 120
ROM_CAUTION_THRESHOLD_DEG = 90
ROM_RESET_AFTER_SECONDS = 8.0
ROM_EXERCISE_KEY = "rom_shoulder"


def _vector_angle(vector_a, vector_b):
    norm_a = np.linalg.norm(vector_a)
    norm_b = np.linalg.norm(vector_b)
    if norm_a == 0 or norm_b == 0:
        return None
    cosine = np.dot(vector_a / norm_a, vector_b / norm_b)
    return float(np.degrees(np.arccos(np.clip(cosine, -1.0, 1.0))))


def _joint_angle(point_a, point_b, point_c):
    return _vector_angle(point_a - point_b, point_c - point_b)


def _point(landmarks, name):
    return np.array(landmarks[name]["world"], dtype=np.float32)


def _arm_raise_angle(shoulder, elbow, hip_center):
    angle = _vector_angle(elbow - shoulder, shoulder - hip_center)
    if angle is None:
        return None
    return max(0.0, min(180.0, 180.0 - angle))


def calculate_shoulder_rom_metrics(landmarks):
    left_shoulder = _point(landmarks, "LEFT_SHOULDER")
    right_shoulder = _point(landmarks, "RIGHT_SHOULDER")
    left_elbow = _point(landmarks, "LEFT_ELBOW")
    right_elbow = _point(landmarks, "RIGHT_ELBOW")
    left_wrist = _point(landmarks, "LEFT_WRIST")
    right_wrist = _point(landmarks, "RIGHT_WRIST")
    left_hip = _point(landmarks, "LEFT_HIP")
    right_hip = _point(landmarks, "RIGHT_HIP")
    hip_center = (left_hip + right_hip) / 2.0

    left_raise = _arm_raise_angle(left_shoulder, left_elbow, hip_center)
    right_raise = _arm_raise_angle(right_shoulder, right_elbow, hip_center)
    left_elbow_angle = _joint_angle(left_shoulder, left_elbow, left_wrist)
    right_elbow_angle = _joint_angle(right_shoulder, right_elbow, right_wrist)
    available_angles = [
        angle for angle in (left_raise, right_raise) if angle is not None
    ]
    current_angle = max(available_angles) if available_angles else None

    return {
        "current_angle": current_angle,
        "left_arm_raise_deg": left_raise,
        "right_arm_raise_deg": right_raise,
        "left_elbow_deg": left_elbow_angle,
        "right_elbow_deg": right_elbow_angle,
    }


class ShoulderROMTracker:
    def __init__(self):
        self.reset()

    def reset(self):
        self.max_angle = 0
        self.last_update = time.monotonic()

    def analyze(self, landmarks):
        self.last_update = time.monotonic()

        metrics = calculate_shoulder_rom_metrics(landmarks)
        current_angle = metrics["current_angle"]
        if current_angle is None:
            return _rom_result(
                state="LOW_VISIBILITY",
                current_angle=0,
                max_angle=self.max_angle,
                rom_status="인식 실패",
                feedback="사람이 화면에 충분히 보이도록 한 뒤 다시 시도해주세요.",
            )

        rounded_current = round(current_angle)
        self.max_angle = max(self.max_angle, rounded_current)

        if self.max_angle >= ROM_NORMAL_THRESHOLD_DEG:
            state = "NORMAL_RANGE"
            status = "정상 범위"
            feedback = "가동 범위가 충분합니다. 현재 범위에서 안전하게 운동을 진행하세요."
        elif self.max_angle >= ROM_CAUTION_THRESHOLD_DEG:
            state = "NEEDS_CAUTION"
            status = "주의 필요"
            feedback = "가동 범위가 다소 부족합니다. 무리하지 말고 천천히 반복하세요."
        else:
            state = "MEASURING"
            status = "측정 중"
            feedback = "화면을 보며 팔을 천천히 들어올려주세요."

        result = _rom_result(
            state=state,
            current_angle=rounded_current,
            max_angle=self.max_angle,
            rom_status=status,
            feedback=feedback,
        )
        result.update(
            {
                "left_arm_raise_deg": _round_or_none(metrics["left_arm_raise_deg"]),
                "right_arm_raise_deg": _round_or_none(metrics["right_arm_raise_deg"]),
                "left_elbow_deg": _round_or_none(metrics["left_elbow_deg"]),
                "right_elbow_deg": _round_or_none(metrics["right_elbow_deg"]),
            }
        )
        return result


def _rom_result(state, current_angle, max_angle, rom_status, feedback):
    accuracy = min(100, round((max_angle / ROM_NORMAL_THRESHOLD_DEG) * 100))
    return {
        "accuracy": accuracy,
        "angle": current_angle,
        "target_angle": ROM_NORMAL_THRESHOLD_DEG,
        "current_angle": current_angle,
        "max_angle": max_angle,
        "rom_status": rom_status,
        "feedback": feedback,
        "state": state,
        "stage": 1,
        "completed_stages": 1 if state == "NORMAL_RANGE" else 0,
        "total_stages": 1,
        "instruction": "화면을 보며 팔을 천천히 들어올려주세요.",
        "result_note": "본 결과는 운동 보조용 참고 정보이며 의학적 진단이 아닙니다.",
        "feedback_summary": f"최대 가동 범위 {max_angle}도, {rom_status}로 측정되었습니다.",
    }


def _round_or_none(value):
    return round(value) if value is not None else None


def _unavailable_result(state, feedback):
    return _rom_result(
        state=state,
        current_angle=0,
        max_angle=_rom_tracker.max_angle,
        rom_status="인식 실패",
        feedback=feedback,
    )


_rom_tracker = ShoulderROMTracker()


def reset_rom_check(exercise_key=ROM_EXERCISE_KEY):
    if exercise_key == ROM_EXERCISE_KEY:
        _rom_tracker.reset()


def analyze_rom_frame(frame, exercise_key=ROM_EXERCISE_KEY):
    pose = detect_pose(frame)
    metadata = {"tracking": pose.get("tracking", {}), "analysis_valid": pose.get("analysis_valid", True)}
    if pose["state"] in INVALID_EXERCISE_ANALYSIS_STATES:
        return {**_unavailable_result(pose["state"], UNAVAILABLE_EXERCISE_FEEDBACK[pose["state"]]), **metadata}
    return {**_rom_tracker.analyze(pose["landmarks"]), **metadata}
