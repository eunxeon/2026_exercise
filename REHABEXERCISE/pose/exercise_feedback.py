import time

import numpy as np

from pose.pose_detector import detect_pose


POSE_SEQUENCE = ("pose1_left", "pose2_center", "pose3_right")
HOLD_THRESHOLD = 4
STAGE_COOLDOWN_FRAMES = 5

# Values sampled from shoulder.mp4 at 4.75s, 5.25s, and 6.75s.
REFERENCE_METRICS = {
    "pose1_left": {
        "left_arm_raise_deg": 161.5,
        "right_arm_raise_deg": 154.0,
        "left_elbow_deg": 164.0,
        "right_elbow_deg": 158.0,
        "face_rotation_deg": -22.9,
    },
    "pose2_center": {
        "left_arm_raise_deg": 158.1,
        "right_arm_raise_deg": 147.0,
        "left_elbow_deg": 164.0,
        "right_elbow_deg": 153.0,
        "face_rotation_deg": 0.3,
    },
    "pose3_right": {
        "left_arm_raise_deg": 44.5,
        "right_arm_raise_deg": 37.0,
        "left_elbow_deg": 167.0,
        "right_elbow_deg": 158.0,
        "face_rotation_deg": 63.1,
    },
}

THRESHOLDS = {
    "left_arm_raise_deg": 40.0,
    "right_arm_raise_deg": 40.0,
    "left_elbow_deg": 35.0,
    "right_elbow_deg": 35.0,
    "face_rotation_deg": 30.0,
}

STAGE_INSTRUCTIONS = {
    "pose1_left": "1단계: 양팔을 올리고 영상처럼 왼쪽으로 돌아주세요.",
    "pose2_center": "2단계: 양팔을 든 채 몸을 정면으로 돌려주세요.",
    "pose3_right": "3단계: 팔을 내리면서 영상처럼 오른쪽으로 돌아주세요.",
}


def _vector_angle(vector_a, vector_b):
    norm_a = np.linalg.norm(vector_a)
    norm_b = np.linalg.norm(vector_b)
    if norm_a == 0 or norm_b == 0:
        return None
    cosine = np.dot(vector_a / norm_a, vector_b / norm_b)
    return float(np.degrees(np.arccos(np.clip(cosine, -1.0, 1.0))))


def _joint_angle(point_a, point_b, point_c):
    return _vector_angle(point_a - point_b, point_c - point_b)


def _point(landmarks, name, coordinate="world"):
    return np.array(landmarks[name][coordinate], dtype=np.float32)


def _signed_offset_angle(center_x, reference_x, scale):
    if not scale:
        return None
    ratio = np.clip((center_x - reference_x) / scale, -1.0, 1.0)
    return float(np.degrees(np.arcsin(ratio)))


def calculate_metrics(landmarks):
    left_shoulder = _point(landmarks, "LEFT_SHOULDER")
    right_shoulder = _point(landmarks, "RIGHT_SHOULDER")
    left_elbow = _point(landmarks, "LEFT_ELBOW")
    right_elbow = _point(landmarks, "RIGHT_ELBOW")
    left_wrist = _point(landmarks, "LEFT_WRIST")
    right_wrist = _point(landmarks, "RIGHT_WRIST")
    left_hip = _point(landmarks, "LEFT_HIP")
    right_hip = _point(landmarks, "RIGHT_HIP")
    hip_center = (left_hip + right_hip) / 2.0

    left_raise = 180.0 - _vector_angle(
        left_elbow - left_shoulder, left_shoulder - hip_center
    )
    right_raise = 180.0 - _vector_angle(
        right_elbow - right_shoulder, right_shoulder - hip_center
    )

    nose = _point(landmarks, "NOSE", "normalized")
    left_eye = _point(landmarks, "LEFT_EYE", "normalized")
    right_eye = _point(landmarks, "RIGHT_EYE", "normalized")
    eye_center = (left_eye + right_eye) / 2.0
    eye_width = abs(right_eye[0] - left_eye[0])

    return {
        "left_arm_raise_deg": left_raise,
        "right_arm_raise_deg": right_raise,
        "left_elbow_deg": _joint_angle(left_shoulder, left_elbow, left_wrist),
        "right_elbow_deg": _joint_angle(right_shoulder, right_elbow, right_wrist),
        "face_rotation_deg": _signed_offset_angle(nose[0], eye_center[0], eye_width),
    }


def _metric_score(value, target, threshold):
    if value is None:
        return 0.0
    return max(0.0, 100.0 * (1.0 - abs(value - target) / threshold))


def evaluate_pose(pose_name, metrics):
    reference = REFERENCE_METRICS[pose_name]
    scoring_keys = (
        "left_arm_raise_deg",
        "right_arm_raise_deg",
        "face_rotation_deg",
    )
    scores = {
        key: _metric_score(metrics.get(key), reference[key], THRESHOLDS[key])
        for key in scoring_keys
    }
    accuracy = round(sum(scores.values()) / len(scores))
    arms_ok = min(scores["left_arm_raise_deg"], scores["right_arm_raise_deg"]) >= 35
    face_ok = scores["face_rotation_deg"] >= 25
    is_correct = arms_ok and face_ok and accuracy >= 60

    average_arm = (
        metrics["left_arm_raise_deg"] + metrics["right_arm_raise_deg"]
    ) / 2.0
    target_arm = (
        reference["left_arm_raise_deg"] + reference["right_arm_raise_deg"]
    ) / 2.0
    feedback = []

    if not arms_ok:
        if average_arm < target_arm:
            feedback.append("양팔을 영상보다 조금 더 올려주세요.")
        else:
            feedback.append("양팔을 영상 높이에 맞게 조금 내려주세요.")
    if not face_ok:
        if pose_name == "pose1_left":
            feedback.append("몸과 고개를 왼쪽으로 더 돌려주세요.")
        elif pose_name == "pose2_center":
            feedback.append("몸과 고개를 정면으로 돌려주세요.")
        else:
            feedback.append("몸과 고개를 오른쪽으로 더 돌려주세요.")

    if is_correct:
        feedback = ["좋습니다. 현재 자세를 잠시 유지해주세요."]
    elif not feedback:
        feedback = ["영상 자세와 비슷합니다. 조금만 더 맞춰주세요."]

    return is_correct, accuracy, " ".join(feedback[:2]), round(average_arm), round(target_arm)


class SequentialExerciseTracker:
    def __init__(self):
        self.reset()

    def reset(self):
        self.current_stage = 0
        self.hold_count = 0
        self.cooldown_count = 0
        self.completed = False
        self.last_update = time.monotonic()

    def analyze(self, landmarks):
        if time.monotonic() - self.last_update > 5.0:
            self.reset()
        self.last_update = time.monotonic()

        if self.completed:
            return self._result(100, "전체 동작을 완료했습니다.", 0, 0)

        pose_name = POSE_SEQUENCE[self.current_stage]
        metrics = calculate_metrics(landmarks)
        is_correct, accuracy, feedback, angle, target_angle = evaluate_pose(
            pose_name, metrics
        )

        if self.cooldown_count > 0:
            self.cooldown_count -= 1
            self.hold_count = 0
            feedback = "다음 동작을 준비하고 가이드 영상을 따라 해주세요."
        elif is_correct:
            self.hold_count += 1
        else:
            self.hold_count = 0

        if self.hold_count >= HOLD_THRESHOLD:
            self.current_stage += 1
            self.hold_count = 0
            self.cooldown_count = STAGE_COOLDOWN_FRAMES
            if self.current_stage >= len(POSE_SEQUENCE):
                self.completed = True
                feedback = "전체 동작을 완료했습니다. 잘하셨어요!"
                accuracy = 100
            else:
                feedback = "단계를 완료했습니다. 다음 동작을 준비해주세요."

        return self._result(accuracy, feedback, angle, target_angle)

    def _result(self, accuracy, feedback, angle, target_angle):
        completed_stages = len(POSE_SEQUENCE) if self.completed else self.current_stage
        stage_index = min(self.current_stage, len(POSE_SEQUENCE) - 1)
        pose_name = POSE_SEQUENCE[stage_index]
        return {
            "accuracy": accuracy,
            "angle": angle,
            "target_angle": target_angle,
            "feedback": feedback,
            "state": "COMPLETE" if self.completed else f"STAGE_{stage_index + 1}",
            "stage": stage_index + 1,
            "completed_stages": completed_stages,
            "total_stages": len(POSE_SEQUENCE),
            "hold_count": self.hold_count,
            "hold_target": HOLD_THRESHOLD,
            "instruction": STAGE_INSTRUCTIONS[pose_name],
        }


_shoulder_tracker = SequentialExerciseTracker()


def reset_exercise(exercise_key="shoulder"):
    if exercise_key == "shoulder":
        _shoulder_tracker.reset()


def _unavailable_result(state, feedback):
    stage_index = min(_shoulder_tracker.current_stage, len(POSE_SEQUENCE) - 1)
    return {
        "accuracy": 0,
        "angle": 0,
        "target_angle": 0,
        "feedback": feedback,
        "state": state,
        "stage": stage_index + 1,
        "completed_stages": _shoulder_tracker.current_stage,
        "total_stages": len(POSE_SEQUENCE),
        "hold_count": 0,
        "hold_target": HOLD_THRESHOLD,
        "instruction": STAGE_INSTRUCTIONS[POSE_SEQUENCE[stage_index]],
    }


def analyze_exercise_frame(frame, exercise_key="shoulder"):
    pose = detect_pose(frame)
    if pose["state"] == "NO_PERSON":
        return _unavailable_result(
            "NO_PERSON", "카메라에 머리부터 허리까지 보이도록 앉아주세요."
        )
    if pose["state"] == "LOW_VISIBILITY":
        return _unavailable_result(
            "LOW_VISIBILITY", "양팔과 얼굴이 잘 보이도록 카메라 위치를 조정해주세요."
        )
    return _shoulder_tracker.analyze(pose["landmarks"])
