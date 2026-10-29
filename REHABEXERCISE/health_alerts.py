import json
import math


ALERT_TYPE_SHOULDER_FUNCTION = "shoulder_function"
ALERT_SEVERITY_BY_STATUS = {
    "caution": "caution",
    "check_required": "warning",
}

ALERT_TITLES = {
    "caution": "운동 기능 상태를 확인해주세요",
    "check_required": "운동 기능 점검이 필요합니다",
}

DEFAULT_ALERT_MESSAGES = {
    "caution": (
        "최근 어깨 운동 또는 관절 가동범위에서 주의가 필요한 변화가 확인되었습니다. "
        "지속적으로 상태를 확인해주세요."
    ),
    "check_required": (
        "최근 관절 가동범위 또는 운동 수행 결과에서 기능 저하 징후가 확인되었습니다. "
        "상태를 지속적으로 확인하고 필요하면 전문가 상담을 고려해주세요."
    ),
}


def build_health_alert_candidate(user_id, health_check):
    overall_status = (health_check or {}).get("overall_status")
    severity = ALERT_SEVERITY_BY_STATUS.get(overall_status)
    if not severity:
        return None

    source_exercise_record_ids = _source_exercise_record_ids(health_check)
    return {
        "user_id": user_id,
        "alert_type": ALERT_TYPE_SHOULDER_FUNCTION,
        "severity": severity,
        "title": ALERT_TITLES[overall_status],
        "message": _build_alert_message(overall_status, health_check),
        "overall_status": overall_status,
        "source_rom_record_id": _source_rom_record_id(health_check),
        "source_exercise_record_ids": json.dumps(
            source_exercise_record_ids,
            ensure_ascii=False,
            separators=(",", ":"),
        ),
    }


def decode_source_exercise_record_ids(value):
    if isinstance(value, list):
        return value
    if not value:
        return []

    try:
        decoded = json.loads(value)
    except (TypeError, ValueError):
        return []
    if not isinstance(decoded, list):
        return []
    return decoded


def _source_rom_record_id(health_check):
    rom = (health_check or {}).get("rom") or {}
    return _to_int_or_none(rom.get("record_id"))


def _source_exercise_record_ids(health_check):
    exercise = (health_check or {}).get("exercise") or {}
    record_ids = exercise.get("record_ids") or []
    return [
        record_id
        for record_id in (_to_int_or_none(value) for value in record_ids)
        if record_id is not None
    ]


def _build_alert_message(overall_status, health_check):
    rom = (health_check or {}).get("rom") or {}
    exercise = (health_check or {}).get("exercise") or {}
    rom_status = rom.get("status") if rom.get("available") else None
    accuracy_status = exercise.get("status") if exercise.get("available") else None

    rom_needs_attention = rom_status in {"caution", "reduced", "severely_reduced"}
    accuracy_needs_attention = accuracy_status in {"caution", "reduced"}

    if rom_needs_attention and accuracy_needs_attention:
        if overall_status == "check_required":
            return (
                "최근 관절 가동범위와 운동 수행 정확도가 모두 점검이 필요한 수준으로 확인되었습니다. "
                "상태를 지속적으로 확인하고 필요하면 전문가 상담을 고려해주세요."
            )
        return (
            "최근 관절 가동범위와 운동 수행 정확도가 모두 주의 수준으로 확인되었습니다. "
            "지속적으로 상태를 확인해주세요."
        )

    if rom_needs_attention:
        angle = _format_measurement(rom.get("angle"))
        if angle:
            if overall_status == "check_required":
                return (
                    f"최근 어깨 관절 가동범위가 {angle}도로 측정되어 기능 저하 징후가 확인되었습니다. "
                    "상태를 지속적으로 확인하고 필요하면 전문가 상담을 고려해주세요."
                )
            return (
                f"최근 어깨 관절 가동범위가 {angle}도로 측정되어 가동범위 감소가 확인되었습니다. "
                "지속적으로 상태를 확인해주세요."
            )

    if accuracy_needs_attention:
        accuracy_avg = _format_percent(exercise.get("accuracy_avg"))
        if accuracy_avg:
            if overall_status == "check_required":
                return (
                    f"최근 어깨 운동 수행 정확도가 {accuracy_avg}%로 낮게 나타나 점검이 필요합니다. "
                    "상태를 지속적으로 확인하고 필요하면 전문가 상담을 고려해주세요."
                )
            return (
                f"최근 어깨 운동 수행 정확도가 {accuracy_avg}%로 낮게 나타났습니다. "
                "지속적으로 상태를 확인해주세요."
            )

    return DEFAULT_ALERT_MESSAGES[overall_status]


def _format_measurement(value):
    number = _to_float_or_none(value)
    if number is None:
        return None
    if number.is_integer():
        return str(int(number))
    return f"{number:.1f}"


def _format_percent(value):
    number = _to_float_or_none(value)
    if number is None:
        return None
    return f"{number:.1f}"


def _to_float_or_none(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _to_int_or_none(value):
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
