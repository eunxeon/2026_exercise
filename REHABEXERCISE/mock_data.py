import copy
import json
import os
import random
import time
from datetime import datetime
from uuid import uuid4

from db import load_env_file
from werkzeug.security import check_password_hash


DEFAULT_DEVICE = {
    "id": "mirror-demo-001",
    "name": "Rehab Mirror Demo",
    "location": "demo-room",
}

PAIRING_SECONDS = 600
CODE_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

USERS = [
    {
        "id": "user-1",
        "user_id": "user-1",
        "name": "김영희",
        "birth_year": None,
        "gender": None,
        "birth_date": None,
        "height_cm": None,
        "weight_kg": None,
        "health_condition": None,
        "program": "어깨·몸통 운동",
        "goal": "관절 가동 범위 유지",
        "memo": "관절 가동 범위 유지",
        "created_at": "2026-08-20T00:00:00Z",
    },
    {
        "id": "user-2",
        "user_id": "user-2",
        "name": "박철수",
        "birth_year": None,
        "gender": None,
        "birth_date": None,
        "height_cm": None,
        "weight_kg": None,
        "health_condition": None,
        "program": "무릎 운동",
        "goal": "낙상 예방",
        "memo": "낙상 예방",
        "created_at": "2026-08-20T00:00:00Z",
    },
]

EXERCISES = [
    {
        "key": "shoulder",
        "name": "앉아서 양팔 들고 몸통 돌리기",
        "category": "어깨·몸통 예방 운동",
        "part": "상체",
        "target": 3,
        "duration": "약 1분",
        "angle": 155,
        "description": "의자에 앉아 양팔을 들고 몸통을 좌우로 천천히 움직입니다.",
        "guide": "가이드 영상에 맞춰 1단계 왼쪽, 2단계 정면, 3단계 오른쪽 순서로 움직입니다.",
        "video_path": "/static/videos/shoulder.mp4",
        "is_today": True,
        "analysis_supported": True,
        "status_label": "분석 가능",
    },
    {
        "key": "rom_shoulder",
        "name": "관절 가동 범위 점검",
        "category": "관절 가동 범위",
        "part": "상체",
        "target": 1,
        "duration": "약 1분",
        "angle": 120,
        "description": "카메라로 어깨 관절 움직임을 인식하여 가동 범위를 확인합니다.",
        "guide": "화면을 보며 팔을 천천히 들어올려주세요.",
        "video_path": "/static/videos/rom_shoulder_demo.mp4",
        "is_today": True,
        "analysis_supported": True,
        "status_label": "점검 가능",
    },
    {
        "key": "knee",
        "name": "무릎 굽혔다 펴기",
        "category": "무릎 질환 예방",
        "part": "하체",
        "target": 15,
        "duration": "약 7분",
        "angle": 70,
        "description": "무릎을 안정적으로 굽혔다 펴며 하체 움직임을 확인합니다.",
        "guide": "의자나 벽을 가까이 두고 통증이 없는 범위에서 진행하세요.",
        "video_path": "/static/videos/knee.mp4",
        "is_today": True,
        "analysis_supported": False,
        "status_label": "준비 중",
        "support_message": "무릎 운동 분석은 추후 지원 예정입니다.",
    },
    {
        "key": "flexibility",
        "name": "옆구리 늘리기",
        "category": "유연성",
        "part": "상체",
        "target": 12,
        "duration": "약 6분",
        "angle": 75,
        "description": "몸통을 천천히 기울여 옆구리와 허리를 이완합니다.",
        "guide": "반동을 주지 말고 편안하게 호흡하며 움직이세요.",
        "video_path": "/static/videos/flexibility.mp4",
        "is_today": True,
        "analysis_supported": False,
        "status_label": "준비 중",
        "support_message": "유연성 운동 분석은 추후 지원 예정입니다.",
    },
    {
        "key": "balance",
        "name": "균형 잡기",
        "category": "낙상 예방",
        "part": "전신",
        "target": 12,
        "duration": "약 7분",
        "angle": 65,
        "description": "자세 흔들림을 줄이고 일상 보행 안정성을 높입니다.",
        "guide": "필요하면 보호자나 벽을 가까이 두고 진행하세요.",
        "video_path": "/static/videos/balance.mp4",
        "is_today": False,
        "analysis_supported": False,
        "status_label": "준비 중",
        "support_message": "균형 운동 분석은 추후 지원 예정입니다.",
    },
]

_pairing_sessions = {}
_exercise_records = []
_health_alerts = []
_next_record_id = 1
_next_alert_id = 1

load_env_file()

GUARDIANS = [
    {
        "guardian_id": "guardian-demo-001",
        "login_id": "demo_guardian",
        "password_hash": os.getenv("DEMO_GUARDIAN_PASSWORD_HASH", ""),
        "name": "데모 보호자",
        "created_at": "2026-08-20T00:00:00Z",
        "updated_at": "2026-08-20T00:00:00Z",
    }
]

GUARDIAN_USER_LINKS = [
    {
        "guardian_id": "guardian-demo-001",
        "user_id": "user-1",
        "created_at": "2026-08-20T00:00:00Z",
    }
]


def _clone(value):
    return copy.deepcopy(value)


def get_current_device():
    return _clone(DEFAULT_DEVICE)


def get_current_device_status_snapshot():
    device = _clone(DEFAULT_DEVICE)
    session = _pairing_sessions.get(device["id"])
    status = "waiting"
    code = ""
    expires_in = 0
    paired_user_id = None

    if session:
        expires_in = max(0, int(session.get("expires_at", 0) - time.time()))
        if session.get("paired"):
            status = "paired"
            paired_user_id = session.get("paired_user_id")
        elif expires_in > 0:
            status = "waiting"
            code = session.get("code", "")
        else:
            status = "expired"

    return {
        "id": device["id"],
        "name": device["name"],
        "pairing_status": status,
        "pairing_code": code,
        "pairing_expires_in": expires_in,
        "paired_user_id": paired_user_id,
    }


def create_pairing_code(device_id):
    code = "".join(random.choice(CODE_CHARS) for _ in range(6))
    expires_at = time.time() + PAIRING_SECONDS
    _pairing_sessions[device_id] = {
        "code": code,
        "expires_at": expires_at,
        "paired": False,
        "paired_user_id": None,
    }
    return {
        "device_id": device_id,
        "code": code,
        "expires_in": PAIRING_SECONDS,
        "expires_at": int(expires_at),
    }


def get_pairing_status(device_id):
    session = _pairing_sessions.get(device_id)
    if not session:
        create_pairing_code(device_id)
        session = _pairing_sessions[device_id]

    remaining = max(0, int(session["expires_at"] - time.time()))
    if remaining == 0:
        session["paired"] = False

    return {
        "device_id": device_id,
        "code": session["code"],
        "paired": session["paired"],
        "status": "paired" if session["paired"] else "waiting",
        "expires_in": remaining,
    }


def complete_pairing_for_demo(device_id):
    if device_id not in _pairing_sessions:
        create_pairing_code(device_id)
    _pairing_sessions[device_id]["paired"] = True
    _pairing_sessions[device_id]["paired_user_id"] = USERS[0]["id"] if USERS else None
    return get_pairing_status(device_id)


def pair_device(guardian_id, user_id, pairing_code):
    normalized_code = str(pairing_code).strip().upper()
    device_id = None
    session = None
    for current_device_id, current_session in _pairing_sessions.items():
        if str(current_session.get("code", "")).upper() == normalized_code:
            device_id = current_device_id
            session = current_session
            break

    if not session:
        raise ValueError("pairing code not found")
    if session.get("paired"):
        raise ValueError("pairing code already used")
    if int(session["expires_at"] - time.time()) <= 0:
        raise ValueError("pairing code expired")
    if not any(account["guardian_id"] == guardian_id for account in GUARDIANS):
        raise ValueError("guardian not found")
    if not any(
        link["guardian_id"] == guardian_id and link["user_id"] == user_id
        for link in GUARDIAN_USER_LINKS
    ):
        raise ValueError("guardian user link not found")

    session["paired"] = True
    session["paired_user_id"] = user_id
    return {
        "mirror_id": device_id,
        "device_name": DEFAULT_DEVICE["name"]
        if device_id == DEFAULT_DEVICE["id"]
        else "Rehab Mirror Demo",
        "pairing_status": "paired",
        "paired_user_id": user_id,
    }


def list_users(device_id):
    return _clone(USERS)


def list_exercises():
    return _clone(EXERCISES)


def create_exercise_record(record):
    global _next_record_id
    saved_record = {
        "record_id": _next_record_id,
        "user_id": record["user_id"],
        "exercise_key": record["exercise_key"],
        "accuracy_avg": record.get("accuracy_avg"),
        "feedback_summary": record.get("feedback_summary", ""),
        "started_at": record.get("started_at") or datetime.utcnow().isoformat(),
        "ended_at": record.get("ended_at") or datetime.utcnow().isoformat(),
    }
    _next_record_id += 1
    _exercise_records.append(saved_record)
    return _clone(saved_record)


def list_exercise_records(user_id):
    records = [
        record for record in _exercise_records if record.get("user_id") == user_id
    ]
    return _clone(list(reversed(records)))


def create_health_alert_if_needed(user_id, health_check, candidate):
    if not candidate:
        return {
            "created": False,
            "reason": (health_check or {}).get("overall_status") or "not_needed",
            "alert": None,
        }

    duplicate = next(
        (
            alert
            for alert in _health_alerts
            if alert["user_id"] == user_id
            and alert["overall_status"] == candidate["overall_status"]
            and alert.get("source_rom_record_id") == candidate.get("source_rom_record_id")
            and alert.get("source_exercise_record_ids")
            == candidate.get("source_exercise_record_ids")
        ),
        None,
    )
    if duplicate:
        return {
            "created": False,
            "reason": "duplicate",
            "alert": _public_health_alert(duplicate),
        }

    global _next_alert_id
    now = datetime.utcnow().isoformat() + "Z"
    alert = {
        "alert_id": _next_alert_id,
        "user_id": user_id,
        "alert_type": candidate["alert_type"],
        "severity": candidate["severity"],
        "title": candidate["title"],
        "message": candidate["message"],
        "overall_status": candidate["overall_status"],
        "source_rom_record_id": candidate.get("source_rom_record_id"),
        "source_exercise_record_ids": candidate.get("source_exercise_record_ids")
        or "[]",
        "is_read": False,
        "created_at": now,
    }
    _next_alert_id += 1
    _health_alerts.append(alert)
    return {"created": True, "alert": _public_health_alert(alert)}


def list_guardian_alerts(guardian_id):
    linked_user_ids = {
        link["user_id"]
        for link in GUARDIAN_USER_LINKS
        if link["guardian_id"] == guardian_id
    }
    alerts = [
        alert
        for alert in _health_alerts
        if alert.get("user_id") in linked_user_ids
    ]
    alerts = sorted(
        alerts,
        key=lambda alert: (alert.get("created_at") or "", int(alert["alert_id"])),
        reverse=True,
    )
    return _clone([_public_health_alert(alert) for alert in alerts])


def mark_guardian_alert_read(guardian_id, alert_id):
    try:
        alert_id = int(alert_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("health alert not found") from exc

    linked_user_ids = {
        link["user_id"]
        for link in GUARDIAN_USER_LINKS
        if link["guardian_id"] == guardian_id
    }
    alert = next(
        (
            item
            for item in _health_alerts
            if int(item["alert_id"]) == alert_id
            and item.get("user_id") in linked_user_ids
        ),
        None,
    )
    if not alert:
        raise ValueError("health alert not found")

    alert["is_read"] = True
    return _clone(_public_health_alert(alert))


def _public_guardian(account):
    return {
        "guardian_id": account["guardian_id"],
        "login_id": account["login_id"],
        "name": account["name"],
        "created_at": account.get("created_at"),
        "updated_at": account.get("updated_at"),
    }


def create_guardian_account(guardian_id, login_id, password_hash, name):
    if any(account["login_id"] == login_id for account in GUARDIANS):
        raise ValueError("guardian login_id already exists")

    now = datetime.utcnow().isoformat() + "Z"
    account = {
        "guardian_id": guardian_id,
        "login_id": login_id,
        "password_hash": password_hash,
        "name": name,
        "created_at": now,
        "updated_at": now,
    }
    GUARDIANS.append(account)
    return _clone(_public_guardian(account))


def _public_health_alert(alert):
    user = next(
        (item for item in USERS if item.get("id") == alert.get("user_id")),
        None,
    )
    return {
        "alert_id": int(alert["alert_id"]),
        "user_id": alert["user_id"],
        "user_name": user.get("name") if user else None,
        "alert_type": alert.get("alert_type") or "shoulder_function",
        "severity": alert["severity"],
        "title": alert["title"],
        "message": alert["message"],
        "overall_status": alert["overall_status"],
        "source_rom_record_id": alert.get("source_rom_record_id"),
        "source_exercise_record_ids": _decode_source_exercise_record_ids(
            alert.get("source_exercise_record_ids")
        ),
        "is_read": bool(alert.get("is_read")),
        "created_at": alert.get("created_at"),
    }


def _decode_source_exercise_record_ids(value):
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


def authenticate_guardian(login_id, password):
    account = next(
        (item for item in GUARDIANS if item["login_id"] == login_id),
        None,
    )
    if not account or not account["password_hash"] or not check_password_hash(account["password_hash"], password):
        return None
    return _clone(_public_guardian(account))


def list_guardian_users(guardian_id):
    linked_user_ids = {
        link["user_id"]
        for link in GUARDIAN_USER_LINKS
        if link["guardian_id"] == guardian_id
    }
    return _clone([user for user in USERS if user["id"] in linked_user_ids])


def create_guardian_user(guardian_id, user_payload):
    if not any(account["guardian_id"] == guardian_id for account in GUARDIANS):
        raise ValueError("guardian not found")

    name = (user_payload.get("name") or "").strip()
    if not name:
        raise ValueError("invalid user profile")

    now = datetime.utcnow().isoformat() + "Z"
    user_id = _generate_unique_user_id()
    user = {
        "id": user_id,
        "user_id": user_id,
        "name": name,
        "birth_year": user_payload.get("birth_year"),
        "gender": user_payload.get("gender"),
        "birth_date": user_payload.get("birth_date"),
        "height_cm": user_payload.get("height_cm"),
        "weight_kg": user_payload.get("weight_kg"),
        "health_condition": user_payload.get("health_condition"),
        "program": "질환 예방 운동",
        "goal": user_payload.get("memo") or "개인 맞춤 질환 예방",
        "memo": user_payload.get("memo") or "",
        "created_at": now,
    }
    USERS.append(user)
    GUARDIAN_USER_LINKS.append(
        {
            "guardian_id": guardian_id,
            "user_id": user_id,
            "created_at": now,
        }
    )
    return _clone(user)


def update_guardian_user(guardian_id, user_id, updates):
    if not any(account["guardian_id"] == guardian_id for account in GUARDIANS):
        raise ValueError("guardian not found")
    if not any(
        link["guardian_id"] == guardian_id and link["user_id"] == user_id
        for link in GUARDIAN_USER_LINKS
    ):
        raise ValueError("guardian user link not found")

    user = next((item for item in USERS if item["id"] == user_id), None)
    if not user:
        raise ValueError("guardian user link not found")

    if not updates:
        raise ValueError("invalid user profile")
    if "name" in updates and not (updates.get("name") or "").strip():
        raise ValueError("invalid user profile")

    if updates.get("birth_date") and "birth_year" not in updates:
        updates = {**updates, "birth_year": int(updates["birth_date"][:4])}

    for field, value in updates.items():
        user[field] = value

    user["goal"] = user.get("memo") or "개인 맞춤 질환 예방"
    return _clone(user)


def unlink_guardian_user(guardian_id, user_id):
    if not any(account["guardian_id"] == guardian_id for account in GUARDIANS):
        raise ValueError("guardian not found")

    before_count = len(GUARDIAN_USER_LINKS)
    GUARDIAN_USER_LINKS[:] = [
        link
        for link in GUARDIAN_USER_LINKS
        if not (link["guardian_id"] == guardian_id and link["user_id"] == user_id)
    ]
    if len(GUARDIAN_USER_LINKS) == before_count:
        raise ValueError("guardian user link not found")

    return {
        "guardian_id": guardian_id,
        "user_id": user_id,
        "unlinked": True,
        "deleted_user": False,
        "deleted_exercise_records": False,
    }


def create_guardian_user_link(guardian_id, user_id):
    if not any(account["guardian_id"] == guardian_id for account in GUARDIANS):
        return None
    if not any(user["id"] == user_id for user in USERS):
        return None
    if not any(
        link["guardian_id"] == guardian_id and link["user_id"] == user_id
        for link in GUARDIAN_USER_LINKS
    ):
        GUARDIAN_USER_LINKS.append(
            {
                "guardian_id": guardian_id,
                "user_id": user_id,
                "created_at": datetime.utcnow().isoformat() + "Z",
            }
        )
    return {"guardian_id": guardian_id, "user_id": user_id}


def _generate_unique_user_id():
    existing_ids = {user["id"] for user in USERS}
    for _ in range(20):
        user_id = f"user-{uuid4().hex}"
        if user_id not in existing_ids:
            return user_id
    raise ValueError("invalid user profile")
