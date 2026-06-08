import math

from pose.pose_detector import detect_pose


TARGET_ANGLES = {
    "shoulder": 80,
    "knee": 70,
    "flexibility": 75,
    "balance": 65,
    "strength": 80,
}


def calculate_angle(point_a, point_b, point_c):
    """Calculate the angle made by three 2D points at point_b."""
    ax, ay = point_a
    bx, by = point_b
    cx, cy = point_c

    radians = math.atan2(cy - by, cx - bx) - math.atan2(ay - by, ax - bx)
    angle = abs(math.degrees(radians))
    if angle > 180:
        angle = 360 - angle
    return angle


def evaluate_posture(angle, target_angle):
    """Return a simple accuracy score from the current and target angle."""
    difference = abs(target_angle - angle)
    return max(0, min(100, round(100 - difference * 1.8)))


def get_feedback(accuracy, angle, target_angle):
    """Generate short feedback text for the smart mirror panel."""
    if accuracy >= 90:
        return "분석 연결 성공! 현재 자세가 목표 각도에 가깝습니다."
    if angle < target_angle:
        return "분석 연결 성공! 팔을 조금만 더 올려보세요."
    return "분석 연결 성공! 움직임을 조금 줄이고 천천히 유지해 보세요."


def analyze_exercise_frame(frame, exercise_key="shoulder"):
    """Run the current placeholder pose flow and return UI-ready values."""
    pose = detect_pose(frame)
    landmarks = pose["landmarks"]
    target_angle = TARGET_ANGLES.get(exercise_key, TARGET_ANGLES["shoulder"])

    raw_angle = calculate_angle(
        landmarks["shoulder"],
        landmarks["elbow"],
        landmarks["wrist"],
    )

    # Blend the mock angle with image brightness so live frames visibly update.
    brightness_adjustment = (pose["brightness"] / 255.0) * 18
    angle = round(max(20, min(120, raw_angle * 0.45 + brightness_adjustment)))
    accuracy = evaluate_posture(angle, target_angle)

    return {
        "accuracy": accuracy,
        "angle": angle,
        "target_angle": target_angle,
        "feedback": get_feedback(accuracy, angle, target_angle),
        "state": "TRACKING",
    }
