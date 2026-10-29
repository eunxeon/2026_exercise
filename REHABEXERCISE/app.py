import base64
import binascii
import logging
import os
import socket
import time
import traceback
import uuid
from functools import wraps
from datetime import date
from ipaddress import ip_address

import cv2
import numpy as np
from flask import Flask, jsonify, render_template, request

from data_store import (
    GuardianAlreadyExists,
    GuardianNotFound,
    GuardianUserLinkNotFound,
    HealthAlertNotFound,
    PairingCodeAlreadyUsed,
    PairingCodeExpired,
    PairingCodeNotFound,
    UserValidationError,
    data_store,
)
from pose.pose_detector import analysis_lock, reset_pose_tracking
from pose.exercise_feedback import analyze_exercise_frame, reset_exercise
from pose.rom_checker import ROM_EXERCISE_KEY, analyze_rom_frame, reset_rom_check


app = Flask(__name__)
app.config["JSON_AS_ASCII"] = False
if hasattr(app, "json"):
    app.json.ensure_ascii = False
DEBUG_MODE = os.getenv("DEBUG_MODE", "0").lower() in {"1", "true", "yes", "on"}
SERVER_HOST = "0.0.0.0"
SERVER_PORT = 5000
_last_analysis_state = None
_analysis_session = None
_analysis_mode = None
MAJOR_ANALYSIS_STATES = {
    "STAGE_1",
    "STAGE_2",
    "STAGE_3",
    "COMPLETE",
    "NORMAL_RANGE",
    "NEEDS_CAUTION",
}
AUTO_HEALTH_ALERT_EXERCISE_KEYS = {"shoulder", ROM_EXERCISE_KEY}

if not DEBUG_MODE:
    logging.getLogger("werkzeug").setLevel(logging.ERROR)


def debug_log(message):
    if DEBUG_MODE:
        print(message, flush=True)


def is_lan_ipv4(value):
    try:
        address = ip_address(value)
    except ValueError:
        return False

    return (
        address.version == 4
        and address.is_private
        and not address.is_loopback
        and not address.is_link_local
        and not address.is_multicast
        and not address.is_unspecified
    )


def get_local_lan_ipv4():
    candidates = []

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("8.8.8.8", 80))
            candidates.append(probe.getsockname()[0])
    except OSError:
        pass

    try:
        hostname = socket.gethostname()
        for result in socket.getaddrinfo(hostname, None, socket.AF_INET):
            candidates.append(result[4][0])
    except OSError:
        pass

    for candidate in dict.fromkeys(candidates):
        if is_lan_ipv4(candidate):
            return candidate
    return None


def format_remaining_time(total_seconds):
    total_seconds = max(0, int(total_seconds or 0))
    minutes, seconds = divmod(total_seconds, 60)
    return f"{minutes}분 {seconds}초"


def mirror_status_lines():
    try:
        mirror = data_store.get_current_device_status_snapshot()
    except Exception as exc:
        return ["[현재 스마트미러]", f"상태 확인 실패: {exc}"]

    if not mirror:
        return ["[현재 스마트미러]", "상태 확인 실패: 등록된 스마트미러 없음"]

    status = mirror.get("pairing_status") or "waiting"
    lines = [
        "[현재 스마트미러]",
        f"ID: {mirror.get('id') or '-'}",
        f"이름: {mirror.get('name') or '-'}",
        f"상태: {status}",
    ]

    paired_user_id = mirror.get("paired_user_id")
    if status == "paired":
        lines.append(f"연결 사용자: {paired_user_id or '-'}")
        return lines

    pairing_code = mirror.get("pairing_code") or ""
    expires_in = int(mirror.get("pairing_expires_in") or 0)
    if pairing_code and expires_in > 0:
        lines.extend(
            [
                f"연결 코드: {pairing_code}",
                f"남은 시간: {format_remaining_time(expires_in)}",
            ]
        )
    else:
        lines.extend(
            [
                "현재 사용 가능한 연결 코드 없음",
                "스마트미러 화면에서 새 코드를 발급하세요.",
            ]
        )
    return lines


def print_startup_access_guide():
    pc_base_url = f"http://127.0.0.1:{SERVER_PORT}/"
    emulator_base_url = f"http://10.0.2.2:{SERVER_PORT}/"
    lan_ip = get_local_lan_ipv4()

    lines = [
        "=" * 60,
        "REHABEXERCISE 서버 실행",
        "=" * 60,
        "",
        "[PC 스마트미러 웹 화면]",
        "PC Chrome/Edge에서 스마트미러 웹 화면을 여는 주소",
        pc_base_url,
        "",
        "[서버 상태 확인]",
        f"{pc_base_url}health",
        "",
        "[현재 기기 API]",
        f"{pc_base_url}api/devices/current",
        "",
        "[Android Emulator BASE_URL]",
        "Android Emulator가 PC의 Flask 서버에 접근할 때 사용하는 주소",
        emulator_base_url,
        "",
        "[같은 Wi-Fi 실제 스마트폰 접속 주소]",
        "PC와 실제 Android 스마트폰이 같은 Wi-Fi에 연결된 경우 사용",
    ]

    if lan_ip:
        lines.append(f"http://{lan_ip}:{SERVER_PORT}/")
    else:
        lines.extend(["LAN 주소 확인 실패", "ipconfig에서 IPv4 주소를 확인하세요."])

    lines.extend(["", *mirror_status_lines(), "", "=" * 60])
    print("\n".join(lines), flush=True)


def text_field(payload, field):
    value = payload.get(field)
    if value is None:
        return ""
    return str(value).strip()


def guardian_response(guardian):
    return {
        "guardian": guardian,
        "guardian_id": guardian["guardian_id"],
        "login_id": guardian["login_id"],
        "name": guardian["name"],
    }


class RequestValidationError(ValueError):
    """Raised when an API payload has invalid user input."""


USER_TEXT_LIMITS = {
    "name": 80,
    "gender": 20,
    "health_condition": 500,
    "memo": 500,
}
USER_NUMERIC_LIMITS = {
    "height_cm": (0, 300),
    "weight_kg": (0, 500),
}
USER_PROFILE_FIELDS = {
    "name",
    "gender",
    "birth_date",
    "birth_year",
    "height_cm",
    "weight_kg",
    "health_condition",
    "memo",
}


def _nullable_text(payload, field, *, required=False):
    if field not in payload:
        if required:
            raise RequestValidationError(f"{field} is required")
        return None, False

    value = payload.get(field)
    if value is None:
        if required:
            raise RequestValidationError(f"{field} is required")
        return None, True

    value = str(value).strip()
    if not value:
        if required:
            raise RequestValidationError(f"{field} is required")
        return None, True

    max_length = USER_TEXT_LIMITS[field]
    if len(value) > max_length:
        raise RequestValidationError(f"{field} is too long")
    return value, True


def _nullable_int(payload, field):
    if field not in payload:
        return None, False

    value = payload.get(field)
    if value in (None, ""):
        return None, True

    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise RequestValidationError(f"{field} must be an integer") from exc

    current_year = date.today().year
    if parsed < 1900 or parsed > current_year:
        raise RequestValidationError(f"{field} must be between 1900 and {current_year}")
    return parsed, True


def _nullable_number(payload, field):
    if field not in payload:
        return None, False

    value = payload.get(field)
    if value in (None, ""):
        return None, True

    try:
        parsed = round(float(value), 2)
    except (TypeError, ValueError) as exc:
        raise RequestValidationError(f"{field} must be a number") from exc

    lower, upper = USER_NUMERIC_LIMITS[field]
    if parsed <= lower or parsed > upper:
        raise RequestValidationError(f"{field} must be greater than {lower} and at most {upper}")
    return parsed, True


def _nullable_birth_date(payload):
    if "birth_date" not in payload:
        return None, False

    value = payload.get("birth_date")
    if value in (None, ""):
        return None, True

    try:
        parsed = date.fromisoformat(str(value).strip())
    except ValueError as exc:
        raise RequestValidationError("birth_date must be YYYY-MM-DD") from exc

    current_year = date.today().year
    if parsed.year < 1900 or parsed.year > current_year:
        raise RequestValidationError(f"birth_date year must be between 1900 and {current_year}")
    return parsed.isoformat(), True


def parse_user_profile_payload(payload, *, partial):
    if not isinstance(payload, dict):
        raise RequestValidationError("JSON body must be an object")

    parsed = {}
    field_seen = any(field in payload for field in USER_PROFILE_FIELDS)
    if partial and not field_seen:
        raise RequestValidationError("no updatable user fields were provided")

    name, name_seen = _nullable_text(payload, "name", required=not partial)
    if name_seen or not partial:
        parsed["name"] = name

    for field in ("gender", "health_condition", "memo"):
        value, seen = _nullable_text(payload, field)
        if seen:
            parsed[field] = value

    birth_date, birth_date_seen = _nullable_birth_date(payload)
    if birth_date_seen:
        parsed["birth_date"] = birth_date

    birth_year, birth_year_seen = _nullable_int(payload, "birth_year")
    if birth_year_seen:
        parsed["birth_year"] = birth_year

    if birth_date_seen and birth_date is not None:
        birth_date_year = date.fromisoformat(birth_date).year
        if birth_year_seen and birth_year not in (None, birth_date_year):
            raise RequestValidationError("birth_year must match birth_date year")
        parsed["birth_year"] = birth_date_year

    for field in ("height_cm", "weight_kg"):
        value, seen = _nullable_number(payload, field)
        if seen:
            parsed[field] = value

    return parsed


def api_error(message, status_code):
    return jsonify({"success": False, "error": message}), status_code


def create_health_alert_after_exercise_save(record):
    if not record:
        return None

    exercise_key = record.get("exercise_key")
    if exercise_key not in AUTO_HEALTH_ALERT_EXERCISE_KEYS:
        return None

    user_id = record.get("user_id")
    if not user_id or record.get("record_id") is None:
        return None

    try:
        return data_store.create_health_alert_if_needed(user_id)
    except Exception:
        app.logger.exception(
            "post-save health alert processing failed: user_id=%s record_id=%s exercise_key=%s",
            user_id,
            record.get("record_id"),
            exercise_key,
        )
        return None


@app.route("/")
def index():
    """Render the smart mirror UI."""
    return render_template("index.html")


@app.route("/health")
def health():
    """Simple endpoint for Raspberry Pi connection checks."""
    return jsonify({"status": "ok"})


@app.route("/api/devices/current")
def current_device():
    """Return the demo mirror device metadata."""
    return jsonify({"success": True, "device": data_store.get_current_device()})


@app.route("/api/devices/<device_id>/pairing-code", methods=["POST"])
def issue_pairing_code(device_id):
    """Create a server-side demo pairing code."""
    return jsonify({"success": True, **data_store.create_pairing_code(device_id)})


@app.route("/api/devices/<device_id>/pairing-status")
def pairing_status(device_id):
    """Return the current demo pairing state."""
    return jsonify({"success": True, **data_store.get_pairing_status(device_id)})


@app.route("/api/devices/<device_id>/pairing-status/demo-complete", methods=["POST"])
def demo_complete_pairing(device_id):
    """Presentation helper that marks the demo device as paired."""
    return jsonify({"success": True, **data_store.complete_pairing_for_demo(device_id)})


@app.route("/api/devices/pair", methods=["POST"])
def pair_device():
    """Pair a mirror device to a guardian-managed user using a six-character code."""
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return api_error("JSON body must be an object", 400)

    guardian_id = text_field(payload, "guardian_id")
    user_id = text_field(payload, "user_id")
    pairing_code = text_field(payload, "pairing_code").upper()
    missing_fields = [
        field
        for field, value in (
            ("guardian_id", guardian_id),
            ("user_id", user_id),
            ("pairing_code", pairing_code),
        )
        if not value
    ]
    if missing_fields:
        return api_error(f"missing required fields: {', '.join(missing_fields)}", 400)
    if len(pairing_code) != 6:
        return api_error("pairing_code must be 6 characters", 400)

    try:
        device = data_store.pair_device(guardian_id, user_id, pairing_code)
    except PairingCodeNotFound:
        return api_error("pairing code not found", 404)
    except PairingCodeExpired:
        return api_error("pairing code expired", 410)
    except PairingCodeAlreadyUsed:
        return api_error("pairing code already used or device already paired", 409)
    except GuardianNotFound:
        return api_error("guardian not found", 404)
    except GuardianUserLinkNotFound:
        return api_error("guardian is not linked to user", 403)

    return jsonify({"success": True, "device": device})


@app.route("/api/devices/<device_id>/users")
def device_users(device_id):
    """Return demo users for the selected mirror device."""
    return jsonify({"success": True, "device_id": device_id, "users": data_store.list_users(device_id)})


@app.route("/api/users")
def users():
    """Return users for the mirror UI."""
    return jsonify({"success": True, "users": data_store.list_users()})


@app.route("/api/exercises")
def exercises():
    """Return exercise metadata used by the mirror UI."""
    return jsonify({"success": True, "exercises": data_store.list_exercises()})


@app.route("/api/auth/register", methods=["POST"])
def register_guardian():
    """Create an Android guardian account."""
    payload = request.get_json(silent=True) or {}
    login_id = text_field(payload, "login_id")
    password = text_field(payload, "password")
    name = text_field(payload, "name")
    missing_fields = [
        field
        for field, value in (
            ("login_id", login_id),
            ("password", password),
            ("name", name),
        )
        if not value
    ]
    if missing_fields:
        return (
            jsonify(
                {
                    "success": False,
                    "error": f"missing required fields: {', '.join(missing_fields)}",
                }
            ),
            400,
        )
    if len(login_id) > 80:
        return jsonify({"success": False, "error": "login_id is too long"}), 400
    if len(name) > 80:
        return jsonify({"success": False, "error": "name is too long"}), 400

    try:
        guardian = data_store.create_guardian_account(login_id, password, name)
    except GuardianAlreadyExists:
        return jsonify({"success": False, "error": "login_id already exists"}), 409

    return jsonify({"success": True, **guardian_response(guardian)}), 201


@app.route("/api/auth/login", methods=["POST"])
def login_guardian():
    """Verify an Android guardian account login."""
    payload = request.get_json(silent=True) or {}
    login_id = text_field(payload, "login_id")
    password = text_field(payload, "password")
    missing_fields = [
        field
        for field, value in (("login_id", login_id), ("password", password))
        if not value
    ]
    if missing_fields:
        return (
            jsonify(
                {
                    "success": False,
                    "error": f"missing required fields: {', '.join(missing_fields)}",
                }
            ),
            400,
        )

    guardian = data_store.authenticate_guardian(login_id, password)
    if not guardian:
        return jsonify({"success": False, "error": "invalid login_id or password"}), 401

    return jsonify({"success": True, **guardian_response(guardian)})


@app.route("/api/guardians/<guardian_id>/users", methods=["GET"])
def guardian_users(guardian_id):
    """Return ElderlyUsers linked to one guardian account."""
    users = data_store.list_guardian_users(guardian_id)
    return jsonify({"success": True, "guardian_id": guardian_id, "users": users})


@app.route("/api/guardians/<guardian_id>/users", methods=["POST"])
def create_guardian_user(guardian_id):
    """Create a new elderly user and link the user to one guardian."""
    payload = request.get_json(silent=True) or {}
    try:
        user_payload = parse_user_profile_payload(payload, partial=False)
        user = data_store.create_guardian_user(guardian_id, user_payload)
    except RequestValidationError as exc:
        return api_error(str(exc), 400)
    except UserValidationError as exc:
        return api_error(str(exc), 400)
    except GuardianNotFound:
        return api_error("guardian not found", 404)

    return (
        jsonify(
            {
                "success": True,
                "guardian_id": guardian_id,
                "user": user,
            }
        ),
        201,
    )


@app.route("/api/guardians/<guardian_id>/users/<user_id>", methods=["PATCH"])
def update_guardian_user(guardian_id, user_id):
    """Update a linked elderly user's profile without changing user_id."""
    payload = request.get_json(silent=True) or {}
    try:
        updates = parse_user_profile_payload(payload, partial=True)
        user = data_store.update_guardian_user(guardian_id, user_id, updates)
    except RequestValidationError as exc:
        return api_error(str(exc), 400)
    except UserValidationError as exc:
        return api_error(str(exc), 400)
    except GuardianNotFound:
        return api_error("guardian not found", 404)
    except GuardianUserLinkNotFound:
        return api_error("guardian user link not found", 404)

    return jsonify({"success": True, "guardian_id": guardian_id, "user": user})


@app.route("/api/guardians/<guardian_id>/users/<user_id>", methods=["DELETE"])
def unlink_guardian_user(guardian_id, user_id):
    """Remove only the guardian-user relationship; keep the user and records."""
    try:
        result = data_store.unlink_guardian_user(guardian_id, user_id)
    except GuardianNotFound:
        return api_error("guardian not found", 404)
    except GuardianUserLinkNotFound:
        return api_error("guardian user link not found", 404)

    return jsonify(
        {
            "success": True,
            "guardian_id": guardian_id,
            "user_id": user_id,
            "unlinked": True,
            "deleted_user": False,
            "deleted_exercise_records": False,
            "message": "guardian-user link removed; user profile and exercise records were not deleted",
            "link": result,
        }
    )


@app.route("/api/exercise-records", methods=["POST"])
def create_exercise_record():
    """Save one completed exercise session record."""
    payload = request.get_json(silent=True) or {}
    required_fields = ("user_id", "exercise_key", "started_at", "ended_at")
    missing_fields = [field for field in required_fields if not payload.get(field)]
    if missing_fields:
        return (
            jsonify(
                {
                    "success": False,
                    "error": f"missing required fields: {', '.join(missing_fields)}",
                }
            ),
            400,
        )

    record = data_store.create_exercise_record(payload)
    create_health_alert_after_exercise_save(record)
    return jsonify({"success": True, "record": record})


@app.route("/api/users/<user_id>/exercise-records")
def user_exercise_records(user_id):
    """Return exercise records for one user."""
    records = data_store.list_exercise_records(user_id)
    return jsonify({"success": True, "user_id": user_id, "records": records})


@app.route("/api/users/<user_id>/health-check")
def user_health_check(user_id):
    """Return the current shoulder function check from saved exercise records."""
    result = data_store.get_user_health_check(user_id)
    return jsonify({"success": True, **result})


@app.route("/api/users/<user_id>/health-check/alerts", methods=["POST"])
def create_user_health_check_alert(user_id):
    """Create a guardian-visible movement function alert when needed."""
    health_check = data_store.get_user_health_check(user_id)
    result = data_store.create_health_alert_if_needed(user_id, health_check)
    status_code = 201 if result.get("created") else 200
    return (
        jsonify(
            {
                "success": True,
                "created": bool(result.get("created")),
                "reason": result.get("reason"),
                "alert": result.get("alert"),
                "health_check": health_check,
            }
        ),
        status_code,
    )


@app.route("/api/guardians/<guardian_id>/alerts", methods=["GET"])
def guardian_alerts(guardian_id):
    """Return alerts only for users linked to this guardian."""
    alerts = data_store.list_guardian_alerts(guardian_id)
    return jsonify(
        {
            "success": True,
            "guardian_id": guardian_id,
            "alerts": alerts,
        }
    )


@app.route("/api/guardians/<guardian_id>/alerts/<alert_id>/read", methods=["PATCH"])
def mark_guardian_alert_read(guardian_id, alert_id):
    """Mark one alert as read after guardian-user ownership is verified."""
    try:
        alert = data_store.mark_guardian_alert_read(guardian_id, alert_id)
    except HealthAlertNotFound:
        return api_error("health alert not found", 404)

    return jsonify(
        {
            "success": True,
            "guardian_id": guardian_id,
            "alert": alert,
        }
    )


def decode_data_url_frame(frame_data_url):
    """Convert a browser canvas data URL into an OpenCV BGR frame."""
    if not frame_data_url or "," not in frame_data_url:
        raise ValueError("image data URL is missing or invalid")

    header, encoded = frame_data_url.split(",", 1)
    if "base64" not in header:
        raise ValueError("image data URL must be base64 encoded")

    try:
        image_bytes = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("image data URL has invalid base64 data") from exc
    if not image_bytes:
        raise ValueError("image data URL is empty")

    image_array = np.frombuffer(image_bytes, dtype=np.uint8)
    try:
        frame = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
    except cv2.error as exc:
        raise ValueError("OpenCV could not decode the image") from exc
    if frame is None:
        raise ValueError("OpenCV could not decode the image")
    return frame


def serialized_analysis(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        with analysis_lock:
            return function(*args, **kwargs)
    return wrapped


@app.route("/stop_exercise", methods=["POST"])
@serialized_analysis
def stop_exercise_state():
    global _analysis_session, _analysis_mode
    payload = request.get_json(silent=True) or {}
    if payload.get("analysis_session") != _analysis_session:
        return api_error("stale analysis session", 409)
    reset_pose_tracking()
    _analysis_session, _analysis_mode = uuid.uuid4().hex, None
    return jsonify({"success": True})


@app.route("/analyze_frame", methods=["POST"])
@serialized_analysis
def analyze_frame():
    """Receive one camera frame, run pose analysis, and return JSON."""
    try:
        payload = request.get_json(silent=True) or {}
        if _analysis_session is not None and payload.get("analysis_session") != _analysis_session:
            return api_error("stale analysis session", 409)
        requested_mode = payload.get("mode", payload.get("exercise_key", "shoulder"))
        if _analysis_mode is not None and requested_mode != _analysis_mode:
            return api_error("exercise mode changed; reset first", 409)
        frame_data_url = payload.get("image")

        analysis_started = time.monotonic()
        frame = decode_data_url_frame(frame_data_url)
        debug_log(f"[/analyze_frame] decoded frame: {frame.shape[1]}x{frame.shape[0]}")

        exercise_key = payload.get("exercise_key", "shoulder")
        mode = payload.get("mode", exercise_key)
        if mode == ROM_EXERCISE_KEY or exercise_key == ROM_EXERCISE_KEY:
            result = analyze_rom_frame(frame, exercise_key=ROM_EXERCISE_KEY)
        else:
            result = analyze_exercise_frame(frame, exercise_key=exercise_key)
        debug_log(
            "[/analyze_frame] "
            f"angle={result.get('angle')} "
            f"accuracy={result.get('accuracy')} "
            f"state={result.get('state')}"
        )

        global _last_analysis_state
        current_state = result.get("state")
        if current_state != _last_analysis_state:
            if DEBUG_MODE or current_state in MAJOR_ANALYSIS_STATES:
                print(
                    f"[analysis] state: {_last_analysis_state or 'START'} -> {current_state}",
                    flush=True,
                )
            _last_analysis_state = current_state

        result["analysis_latency_ms"] = round((time.monotonic() - analysis_started) * 1000, 1)
        return jsonify({"success": True, **result})
    except Exception as exc:
        print(f"[/analyze_frame] error: {exc}", flush=True)
        if DEBUG_MODE:
            traceback.print_exc()
        return jsonify({"success": False, "error": str(exc)}), 400


@app.route("/reset_exercise", methods=["POST"])
@serialized_analysis
def reset_exercise_state():
    global _last_analysis_state, _analysis_session, _analysis_mode
    payload = request.get_json(silent=True) or {}
    exercise_key = payload.get("exercise_key", "shoulder")
    mode = payload.get("mode", exercise_key)
    if mode == ROM_EXERCISE_KEY or exercise_key == ROM_EXERCISE_KEY:
        reset_rom_check(ROM_EXERCISE_KEY)
    else:
        reset_exercise(exercise_key)
    reset_pose_tracking()
    # Tokenized UI calls reject frames still in flight from an earlier run.
    _analysis_session = uuid.uuid4().hex if payload.get("use_session") else None
    _analysis_mode = mode
    _last_analysis_state = None
    print(f"[exercise] reset: {exercise_key}", flush=True)
    return jsonify({"success": True, "analysis_session": _analysis_session})


if __name__ == "__main__":
    if not DEBUG_MODE or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        print_startup_access_guide()
    app.run(
        host=SERVER_HOST,
        port=SERVER_PORT,
        debug=DEBUG_MODE,
        use_reloader=DEBUG_MODE,
    )
