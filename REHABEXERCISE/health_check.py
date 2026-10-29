import math
import re
from datetime import datetime, timezone
from decimal import Decimal

from pose.analysis_states import (
    INVALID_EXERCISE_ANALYSIS_FEEDBACKS,
    INVALID_EXERCISE_ANALYSIS_STATES,
)


ROM_EXERCISE_KEY = "rom_shoulder"
SHOULDER_EXERCISE_KEY = "shoulder"
NORMAL_SHOULDER_ROM = 180

ROM_LABELS = {
    "normal": "정상",
    "caution": "주의",
    "reduced": "저하",
    "severely_reduced": "큰 저하",
}
ACCURACY_LABELS = {
    "good": "양호",
    "caution": "주의",
    "reduced": "저하",
}
OVERALL_LABELS = {
    "normal": "이상 징후 없음",
    "caution": "주의 관찰",
    "check_required": "운동 기능 저하 징후 - 점검 권장",
    "insufficient_data": "데이터 부족",
}
OVERALL_MESSAGES = {
    "normal": "최근 어깨 운동 기능에서 뚜렷한 저하 징후가 확인되지 않았습니다.",
    "caution": "최근 어깨 운동 기능에 주의 관찰이 필요한 변화가 있어 지속적인 관찰을 권장합니다.",
    "check_required": "최근 어깨 운동 기능 저하 징후가 확인되어 점검을 권장합니다.",
    "insufficient_data": "어깨 운동 기능 점검에 필요한 최근 기록이 부족합니다.",
}

ROM_ANGLE_PATTERN = re.compile(r"최대\s*가동\s*범위\s*(\d+(?:\.\d+)?)\s*도")


def parse_rom_angle(feedback_summary):
    if not feedback_summary:
        return None

    match = ROM_ANGLE_PATTERN.search(str(feedback_summary))
    if not match:
        return None

    try:
        angle = float(match.group(1))
    except ValueError:
        return None

    if not math.isfinite(angle):
        return None
    if angle.is_integer():
        return int(angle)
    return round(angle, 1)


def classify_rom(angle):
    if angle >= 144:
        return "normal"
    if angle >= 90:
        return "caution"
    if angle >= 45:
        return "reduced"
    return "severely_reduced"


def classify_accuracy(accuracy):
    if accuracy >= 80:
        return "good"
    if accuracy >= 60:
        return "caution"
    return "reduced"


def build_shoulder_health_check(user_id, records):
    sorted_records = _sort_records(records or [])
    rom = _build_rom_result(sorted_records)
    exercise = _build_exercise_result(sorted_records)
    overall_status = _overall_status(
        rom.get("status") if rom.get("available") else None,
        exercise.get("status") if exercise.get("available") else None,
    )

    return {
        "user_id": user_id,
        "overall_status": overall_status,
        "overall_label": OVERALL_LABELS[overall_status],
        "rom": rom,
        "exercise": exercise,
        "message": OVERALL_MESSAGES[overall_status],
    }


def _build_rom_result(records):
    rom_records = [
        record
        for record in records
        if record.get("exercise_key") == ROM_EXERCISE_KEY
    ]
    latest = rom_records[0] if rom_records else None
    if not latest:
        return {
            "available": False,
            "normal_max": NORMAL_SHOULDER_ROM,
            "label": "데이터 없음",
            "reason": "no_rom_record",
        }

    angle = parse_rom_angle(latest.get("feedback_summary"))
    if angle is None:
        return {
            "available": False,
            "record_id": latest.get("record_id"),
            "normal_max": NORMAL_SHOULDER_ROM,
            "label": "데이터 없음",
            "reason": "rom_angle_not_found",
        }

    status = classify_rom(angle)
    percentage = angle / NORMAL_SHOULDER_ROM * 100
    reduction_percentage = (NORMAL_SHOULDER_ROM - angle) / NORMAL_SHOULDER_ROM * 100
    return {
        "available": True,
        "record_id": latest.get("record_id"),
        "angle": angle,
        "normal_max": NORMAL_SHOULDER_ROM,
        "percentage": round(percentage, 1),
        "reduction_percentage": round(reduction_percentage, 1),
        "status": status,
        "label": ROM_LABELS[status],
        "started_at": latest.get("started_at"),
    }


def _build_exercise_result(records):
    valid_records = []
    for record in records:
        if record.get("exercise_key") != SHOULDER_EXERCISE_KEY:
            continue
        accuracy = _to_float(record.get("accuracy_avg"))
        if accuracy is None:
            continue
        if _is_invalid_exercise_analysis(record):
            continue
        valid_records.append((record, accuracy))

    recent = valid_records[:3]
    if not recent:
        return {
            "available": False,
            "recent_count": 0,
            "label": "데이터 없음",
            "reason": "no_valid_accuracy",
        }

    average = sum(accuracy for _, accuracy in recent) / len(recent)
    accuracy_avg = round(average, 1)
    status = classify_accuracy(accuracy_avg)
    return {
        "available": True,
        "recent_count": len(recent),
        "record_ids": [record.get("record_id") for record, _ in recent],
        "accuracy_avg": accuracy_avg,
        "status": status,
        "label": ACCURACY_LABELS[status],
    }


def _overall_status(rom_status, accuracy_status):
    if not rom_status and not accuracy_status:
        return "insufficient_data"

    if rom_status in {"reduced", "severely_reduced"} or accuracy_status == "reduced":
        return "check_required"
    if rom_status == "caution" and accuracy_status == "caution":
        return "check_required"
    if rom_status == "caution" or accuracy_status == "caution":
        return "caution"
    return "normal"


def _is_invalid_exercise_analysis(record):
    state = record.get("state") or record.get("analysis_state")
    if state in INVALID_EXERCISE_ANALYSIS_STATES:
        return True

    # ExerciseRecords has no analysis state column yet; keep this summary match
    # as a compatibility shim for existing records saved by pose.exercise_feedback.
    feedback_summary = str(record.get("feedback_summary") or "").strip()
    return feedback_summary in INVALID_EXERCISE_ANALYSIS_FEEDBACKS


def _sort_records(records):
    return sorted(records, key=_record_sort_key, reverse=True)


def _record_sort_key(record):
    return (
        _parse_record_datetime(record.get("started_at")),
        _parse_record_datetime(record.get("ended_at")),
        _to_int(record.get("record_id")),
    )


def _parse_record_datetime(value):
    if isinstance(value, datetime):
        parsed = value
    elif value:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return datetime.min
    else:
        return datetime.min

    if parsed.tzinfo:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _to_float(value):
    if value is None:
        return None
    if isinstance(value, Decimal):
        value = float(value)
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def _to_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return -1
