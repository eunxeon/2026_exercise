import copy
import random
import time


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
        "name": "김영희",
        "program": "어깨·몸통 운동",
        "goal": "관절 가동 범위 유지",
    },
    {
        "id": "user-2",
        "name": "박철수",
        "program": "무릎 운동",
        "goal": "낙상 예방",
    },
]

EXERCISES = [
    {
        "key": "shoulder",
        "name": "앉아서 양팔 들고 몸통 돌리기",
        "category": "어깨·몸통 재활",
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
        "key": "knee",
        "name": "무릎 굽혔다 펴기",
        "category": "무릎 재활",
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


def _clone(value):
    return copy.deepcopy(value)


def get_current_device():
    return _clone(DEFAULT_DEVICE)


def create_pairing_code(device_id):
    code = "".join(random.choice(CODE_CHARS) for _ in range(6))
    expires_at = time.time() + PAIRING_SECONDS
    _pairing_sessions[device_id] = {
        "code": code,
        "expires_at": expires_at,
        "paired": False,
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
    return get_pairing_status(device_id)


def list_users(device_id):
    return _clone(USERS)


def list_exercises():
    return _clone(EXERCISES)
