"""운동 자세 평가와 피드백 계산 함수 모음입니다."""

import math


def calculate_angle(a, b, c):
    """세 점 a-b-c가 이루는 각도를 계산합니다.

    각 점은 {"x": float, "y": float} 형태이거나 (x, y) 튜플일 수 있습니다.
    b 지점을 관절 중심으로 보고 각도를 구합니다.
    """
    ax, ay = _point_to_xy(a)
    bx, by = _point_to_xy(b)
    cx, cy = _point_to_xy(c)

    ba = (ax - bx, ay - by)
    bc = (cx - bx, cy - by)

    dot_product = ba[0] * bc[0] + ba[1] * bc[1]
    ba_length = math.hypot(*ba)
    bc_length = math.hypot(*bc)

    if ba_length == 0 or bc_length == 0:
        return 0.0

    cosine = dot_product / (ba_length * bc_length)
    cosine = max(-1.0, min(1.0, cosine))
    return round(math.degrees(math.acos(cosine)), 2)


def evaluate_posture(current_pose, target_pose):
    """현재 자세와 목표 자세를 비교해 정확도를 계산합니다.

    현재는 같은 관절 key의 x, y 거리 차이를 기반으로 한 단순 평가입니다.
    실제 프로젝트에서는 운동 종류별 기준 각도와 단계 판정 로직으로 확장합니다.
    """
    common_keys = set(current_pose.keys()) & set(target_pose.keys())
    if not common_keys:
        return {"accuracy": 0, "message": "비교할 관절 좌표가 없습니다."}

    total_error = 0.0
    for key in common_keys:
        current_x, current_y = _point_to_xy(current_pose[key])
        target_x, target_y = _point_to_xy(target_pose[key])
        total_error += math.hypot(current_x - target_x, current_y - target_y)

    average_error = total_error / len(common_keys)
    accuracy = max(0, min(100, round(100 - average_error * 100)))

    return {
        "accuracy": accuracy,
        "average_error": round(average_error, 4),
        "message": "평가 완료",
    }


def get_feedback(result):
    """평가 결과에 따라 사용자에게 보여줄 피드백 문구를 반환합니다."""
    accuracy = result.get("accuracy", 0)

    if accuracy >= 90:
        return "좋습니다. 현재 자세를 유지하세요."
    if accuracy >= 70:
        return "거의 맞습니다. 관절 각도를 조금 더 맞춰보세요."
    return "자세를 천천히 다시 잡아보세요."


def _point_to_xy(point):
    """dict 또는 tuple 형태의 좌표를 x, y 값으로 변환합니다."""
    if isinstance(point, dict):
        return float(point.get("x", 0)), float(point.get("y", 0))
    return float(point[0]), float(point[1])
