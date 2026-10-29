import os
import random
import time
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

from db import DatabaseUnavailable, MSSQLDatabase, load_env_file
from health_alerts import build_health_alert_candidate, decode_source_exercise_record_ids
from health_check import build_shoulder_health_check
import mock_data
from werkzeug.security import check_password_hash, generate_password_hash


load_env_file()

PAIRING_SECONDS = int(os.getenv("PAIRING_CODE_TTL_SECONDS", "600"))
CODE_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
DEFAULT_MIRROR_ID = os.getenv(
    "DB_MIRROR_ID", os.getenv("MSSQL_MIRROR_ID", "mirror-demo-001")
)

EXERCISE_UI_DEFAULTS = {
    "shoulder": {
        "category": "어깨·몸통 예방 운동",
        "part": "상체",
        "target": 3,
        "duration": "약 1분",
        "angle": 155,
        "guide": "가이드 영상에 맞춰 1단계 왼쪽, 2단계 정면, 3단계 오른쪽 순서로 움직입니다.",
        "is_today": True,
    },
    "rom_shoulder": {
        "part": "상체",
        "target": 1,
        "duration": "약 1분",
        "angle": 120,
        "guide": "화면을 보며 팔을 천천히 들어올려주세요.",
        "is_today": True,
        "title": "관절 가동 범위 점검",
        "category": "관절 가동 범위",
        "description": "카메라로 어깨 관절 움직임을 인식하여 가동 범위를 확인합니다.",
        "video_path": "/static/videos/rom_shoulder_demo.mp4",
        "is_supported": True,
        "status_label": "점검 가능",
    },
    "knee": {
        "category": "무릎 질환 예방",
        "part": "하체",
        "target": 15,
        "duration": "약 7분",
        "angle": 70,
        "guide": "의자나 벽을 가까이 두고 통증이 없는 범위에서 진행하세요.",
        "is_today": True,
    },
    "flexibility": {
        "category": "유연성",
        "part": "상체",
        "target": 12,
        "duration": "약 6분",
        "angle": 75,
        "guide": "반동을 주지 말고 편안하게 호흡하며 움직이세요.",
        "is_today": True,
    },
    "balance": {
        "category": "낙상 예방",
        "part": "전신",
        "target": 12,
        "duration": "약 7분",
        "angle": 65,
        "guide": "필요하면 보호자나 벽을 가까이 두고 진행하세요.",
        "is_today": False,
    },
}


class DataStoreError(Exception):
    """Base error for expected data-store level failures."""


class GuardianAlreadyExists(DataStoreError):
    """Raised when a guardian login_id is already registered."""


class GuardianNotFound(DataStoreError):
    """Raised when a guardian account does not exist."""


class GuardianUserLinkNotFound(DataStoreError):
    """Raised when a guardian is not linked to the requested user."""


class PairingCodeNotFound(DataStoreError):
    """Raised when no mirror device has the submitted pairing code."""


class PairingCodeExpired(DataStoreError):
    """Raised when a pairing code exists but its TTL has elapsed."""


class PairingCodeAlreadyUsed(DataStoreError):
    """Raised when a pairing code belongs to an already paired device."""


class UserValidationError(DataStoreError):
    """Raised when a user profile change would create invalid data."""


class HealthAlertNotFound(DataStoreError):
    """Raised when a guardian cannot access the requested health alert."""


class SmartMirrorDataStore:
    def __init__(self, database=None):
        self.database = database or MSSQLDatabase()
        self.fallback_enabled = os.getenv("DB_FALLBACK_TO_MOCK", "1").lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        self._fallback_notice_printed = False
        self._mssql_notice_printed = False

    def _fallback(self, reason, fallback_func, *args):
        if not self.fallback_enabled:
            raise reason

        if not self._fallback_notice_printed:
            print(f"[data_store] using mock_data fallback: {reason}", flush=True)
            self._fallback_notice_printed = True
        return fallback_func(*args)

    def _using_mssql(self):
        if not self._mssql_notice_printed:
            print("[data_store] using MSSQL", flush=True)
            self._mssql_notice_printed = True

    def _run(self, db_func, fallback_func, *args, fallback_on_none=True):
        if not self.database.is_configured():
            return self._fallback(
                DatabaseUnavailable("MSSQL is not enabled or configured"),
                fallback_func,
                *args,
            )

        try:
            value = db_func(*args)
            if value is None and fallback_on_none:
                return self._fallback(
                    DatabaseUnavailable("MSSQL returned no rows"), fallback_func, *args
                )
            self._using_mssql()
            return value
        except DataStoreError:
            raise
        except Exception as exc:
            return self._fallback(exc, fallback_func, *args)

    def get_current_device(self):
        return self._run(self._get_current_device_db, mock_data.get_current_device)

    def get_current_device_status_snapshot(self):
        return self._run(
            self._get_current_device_status_snapshot_db,
            mock_data.get_current_device_status_snapshot,
        )

    def create_pairing_code(self, device_id):
        return self._run(
            self._create_pairing_code_db, mock_data.create_pairing_code, device_id
        )

    def get_pairing_status(self, device_id):
        return self._run(
            self._get_pairing_status_db, mock_data.get_pairing_status, device_id
        )

    def complete_pairing_for_demo(self, device_id):
        return self._run(
            self._complete_pairing_for_demo_db,
            mock_data.complete_pairing_for_demo,
            device_id,
        )

    def pair_device(self, guardian_id, user_id, pairing_code):
        try:
            return self._run(
                self._pair_device_db,
                mock_data.pair_device,
                guardian_id,
                user_id,
                pairing_code,
                fallback_on_none=False,
            )
        except ValueError as exc:
            self._raise_expected_pairing_error(exc)

    def list_users(self, device_id=None):
        resolved_device_id = device_id or DEFAULT_MIRROR_ID
        return self._run(
            self._list_users_db, mock_data.list_users, resolved_device_id
        )

    def list_exercises(self):
        return self._run(self._list_exercises_db, mock_data.list_exercises)

    def create_exercise_record(self, record):
        return self._run(
            self._create_exercise_record_db, mock_data.create_exercise_record, record
        )

    def list_exercise_records(self, user_id):
        return self._run(
            self._list_exercise_records_db, mock_data.list_exercise_records, user_id
        )

    def get_user_health_check(self, user_id):
        records = self.list_exercise_records(user_id)
        return build_shoulder_health_check(user_id, records)

    def create_health_alert_if_needed(self, user_id, health_check=None):
        health_check = health_check or self.get_user_health_check(user_id)
        candidate = build_health_alert_candidate(user_id, health_check)
        if not candidate:
            return {
                "created": False,
                "reason": health_check.get("overall_status") or "not_needed",
                "alert": None,
            }

        return self._run(
            self._create_health_alert_if_needed_db,
            mock_data.create_health_alert_if_needed,
            user_id,
            health_check,
            candidate,
            fallback_on_none=False,
        )

    def list_guardian_alerts(self, guardian_id):
        return self._run(
            self._list_guardian_alerts_db,
            mock_data.list_guardian_alerts,
            guardian_id,
            fallback_on_none=False,
        )

    def mark_guardian_alert_read(self, guardian_id, alert_id):
        try:
            alert_id = int(alert_id)
        except (TypeError, ValueError) as exc:
            raise HealthAlertNotFound("health alert not found") from exc

        try:
            return self._run(
                self._mark_guardian_alert_read_db,
                mock_data.mark_guardian_alert_read,
                guardian_id,
                alert_id,
                fallback_on_none=False,
            )
        except ValueError as exc:
            if str(exc) == "health alert not found":
                raise HealthAlertNotFound(str(exc)) from exc
            raise

    def create_guardian_account(self, login_id, password, name):
        guardian_id = f"guardian-{uuid4().hex}"
        password_hash = generate_password_hash(password)
        try:
            return self._run(
                self._create_guardian_account_db,
                mock_data.create_guardian_account,
                guardian_id,
                login_id,
                password_hash,
                name,
            )
        except ValueError as exc:
            if str(exc) == "guardian login_id already exists":
                raise GuardianAlreadyExists(login_id) from exc
            raise

    def authenticate_guardian(self, login_id, password):
        return self._run(
            self._authenticate_guardian_db,
            mock_data.authenticate_guardian,
            login_id,
            password,
            fallback_on_none=False,
        )

    def list_guardian_users(self, guardian_id):
        return self._run(
            self._list_guardian_users_db,
            mock_data.list_guardian_users,
            guardian_id,
        )

    def create_guardian_user(self, guardian_id, user_payload):
        try:
            return self._run(
                self._create_guardian_user_db,
                mock_data.create_guardian_user,
                guardian_id,
                user_payload,
                fallback_on_none=False,
            )
        except ValueError as exc:
            self._raise_expected_user_error(exc)

    def update_guardian_user(self, guardian_id, user_id, updates):
        try:
            return self._run(
                self._update_guardian_user_db,
                mock_data.update_guardian_user,
                guardian_id,
                user_id,
                updates,
                fallback_on_none=False,
            )
        except ValueError as exc:
            self._raise_expected_user_error(exc)

    def unlink_guardian_user(self, guardian_id, user_id):
        try:
            return self._run(
                self._unlink_guardian_user_db,
                mock_data.unlink_guardian_user,
                guardian_id,
                user_id,
                fallback_on_none=False,
            )
        except ValueError as exc:
            self._raise_expected_user_error(exc)

    def create_guardian_user_link(self, guardian_id, user_id):
        return self._run(
            self._create_guardian_user_link_db,
            mock_data.create_guardian_user_link,
            guardian_id,
            user_id,
            fallback_on_none=False,
        )

    def _raise_expected_user_error(self, exc):
        message = str(exc)
        if message == "guardian not found":
            raise GuardianNotFound(message) from exc
        if message == "guardian user link not found":
            raise GuardianUserLinkNotFound(message) from exc
        if message == "invalid user profile":
            raise UserValidationError(message) from exc
        raise exc

    def _raise_expected_pairing_error(self, exc):
        message = str(exc)
        if message == "pairing code not found":
            raise PairingCodeNotFound(message) from exc
        if message == "pairing code expired":
            raise PairingCodeExpired(message) from exc
        if message == "pairing code already used":
            raise PairingCodeAlreadyUsed(message) from exc
        if message == "guardian not found":
            raise GuardianNotFound(message) from exc
        if message == "guardian user link not found":
            raise GuardianUserLinkNotFound(message) from exc
        raise exc

    def _get_current_device_db(self):
        row = self._get_device_row(DEFAULT_MIRROR_ID)
        if not row:
            row = self.database.query_one(
                """
                SELECT TOP 1 mirror_id, device_name
                FROM MirrorDevices
                ORDER BY created_at ASC, mirror_id ASC
                """
            )
        if not row:
            return None

        return {
            "id": row["mirror_id"],
            "name": row["device_name"],
            "location": "mssql",
        }

    def _get_current_device_status_snapshot_db(self):
        row = self._get_device_row(DEFAULT_MIRROR_ID)
        if not row:
            return None

        status = row.get("pairing_status") or "waiting"
        pairing_code = row.get("pairing_code") or ""
        remaining = self._pairing_remaining_seconds(row.get("updated_at"))
        if pairing_code and remaining == 0 and status != "paired":
            status = "expired"

        return {
            "id": row["mirror_id"],
            "name": row["device_name"],
            "pairing_status": status,
            "pairing_code": pairing_code
            if remaining > 0 and status != "paired"
            else "",
            "pairing_expires_in": remaining
            if pairing_code and status != "paired"
            else 0,
            "paired_user_id": row.get("paired_user_id"),
        }

    def _create_pairing_code_db(self, device_id):
        code = "".join(random.choice(CODE_CHARS) for _ in range(6))
        rowcount = self.database.execute(
            """
            UPDATE MirrorDevices
            SET pairing_code = ?,
                pairing_status = ?,
                paired_user_id = NULL,
                updated_at = SYSUTCDATETIME()
            WHERE mirror_id = ?
            """,
            [code, "waiting", device_id],
        )

        if rowcount == 0:
            self.database.execute(
                """
                INSERT INTO MirrorDevices (
                    mirror_id,
                    device_name,
                    pairing_code,
                    pairing_status,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, SYSUTCDATETIME(), SYSUTCDATETIME())
                """,
                [device_id, "Rehab Mirror Demo", code, "waiting"],
            )

        return {
            "device_id": device_id,
            "code": code,
            "expires_in": PAIRING_SECONDS,
            "expires_at": int(time.time() + PAIRING_SECONDS),
        }

    def _get_pairing_status_db(self, device_id):
        row = self._get_device_row(device_id)
        if not row or not row.get("pairing_code"):
            return self._create_pairing_code_db(device_id)

        status = row.get("pairing_status") or "waiting"
        remaining = self._pairing_remaining_seconds(row.get("updated_at"))
        if remaining == 0 and status != "paired":
            status = "expired"

        return {
            "device_id": device_id,
            "code": row.get("pairing_code") or "",
            "paired": status == "paired",
            "status": status,
            "expires_in": remaining,
        }

    def _complete_pairing_for_demo_db(self, device_id):
        user = self.database.query_one(
            """
            SELECT TOP 1 user_id
            FROM ElderlyUsers
            ORDER BY created_at ASC, user_id ASC
            """
        )
        paired_user_id = user["user_id"] if user else None

        if paired_user_id:
            self.database.execute(
                """
                UPDATE MirrorDevices
                SET pairing_status = ?,
                    paired_user_id = ?,
                    updated_at = SYSUTCDATETIME()
                WHERE mirror_id = ?
                """,
                ["paired", paired_user_id, device_id],
            )
        else:
            self.database.execute(
                """
                UPDATE MirrorDevices
                SET pairing_status = ?,
                    updated_at = SYSUTCDATETIME()
                WHERE mirror_id = ?
                """,
                ["paired", device_id],
            )

        return self._get_pairing_status_db(device_id)

    def _pair_device_db(self, guardian_id, user_id, pairing_code):
        normalized_code = str(pairing_code).strip().upper()
        conn = self.database.connect()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT TOP 1
                    mirror_id,
                    device_name,
                    pairing_code,
                    pairing_status,
                    paired_user_id,
                    created_at,
                    updated_at
                FROM MirrorDevices WITH (UPDLOCK, ROWLOCK)
                WHERE UPPER(pairing_code) = ?
                ORDER BY updated_at DESC, mirror_id ASC
                """,
                normalized_code,
            )
            device = self._cursor_row_to_dict(cursor, cursor.fetchone())
            if not device:
                raise PairingCodeNotFound(normalized_code)

            status = device.get("pairing_status") or "waiting"
            if status == "paired" or device.get("paired_user_id"):
                raise PairingCodeAlreadyUsed(normalized_code)
            if status != "waiting":
                raise PairingCodeAlreadyUsed(normalized_code)
            if self._pairing_remaining_seconds(device.get("updated_at")) <= 0:
                raise PairingCodeExpired(normalized_code)

            cursor.execute(
                """
                SELECT guardian_id
                FROM GuardianAccounts
                WHERE guardian_id = ?
                """,
                guardian_id,
            )
            if not cursor.fetchone():
                raise GuardianNotFound(guardian_id)

            cursor.execute(
                """
                SELECT 1
                FROM GuardianUserLinks
                WHERE guardian_id = ?
                    AND user_id = ?
                """,
                guardian_id,
                user_id,
            )
            if not cursor.fetchone():
                raise GuardianUserLinkNotFound(user_id)

            cursor.execute(
                """
                UPDATE MirrorDevices
                SET paired_user_id = ?,
                    pairing_status = ?,
                    updated_at = SYSUTCDATETIME()
                OUTPUT
                    INSERTED.mirror_id,
                    INSERTED.device_name,
                    INSERTED.pairing_code,
                    INSERTED.pairing_status,
                    INSERTED.paired_user_id,
                    INSERTED.created_at,
                    INSERTED.updated_at
                WHERE mirror_id = ?
                    AND pairing_code = ?
                """,
                user_id,
                "paired",
                device["mirror_id"],
                device["pairing_code"],
            )
            paired_device = self._cursor_row_to_dict(cursor, cursor.fetchone())
            conn.commit()
            return self._format_device(paired_device)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _list_users_db(self, device_id):
        rows = self.database.query_all(
            """
            SELECT
                user_id,
                name,
                birth_year,
                gender,
                birth_date,
                height_cm,
                weight_kg,
                health_condition,
                memo,
                created_at
            FROM ElderlyUsers
            ORDER BY created_at ASC, user_id ASC
            """
        )
        if not rows:
            return None

        return [
            self._format_user(row)
            for row in rows
        ]

    def _list_exercises_db(self):
        rows = self.database.query_all(
            """
            SELECT
                exercise_key,
                title,
                category,
                description,
                video_path,
                is_supported,
                status_label
            FROM Exercises
            ORDER BY
                CASE exercise_key
                    WHEN 'shoulder' THEN 1
                    WHEN 'rom_shoulder' THEN 2
                    WHEN 'knee' THEN 3
                    WHEN 'flexibility' THEN 4
                    WHEN 'balance' THEN 5
                    ELSE 99
                END,
                exercise_key ASC
            """
        )
        if not rows:
            return None

        exercises = []
        for row in rows:
            key = row["exercise_key"]
            defaults = EXERCISE_UI_DEFAULTS.get(key, {})
            supported = bool(row.get("is_supported"))
            status_label = row.get("status_label") or (
                "분석 가능" if supported else "준비 중"
            )
            exercises.append(
                {
                    "key": key,
                    "name": row.get("title") or key,
                    "category": defaults.get("category")
                    or row.get("category")
                    or "질환 예방 운동",
                    "part": defaults.get("part", "전신"),
                    "target": defaults.get("target", 1),
                    "duration": defaults.get("duration", "준비 중"),
                    "angle": defaults.get("angle", 0),
                    "description": row.get("description") or "",
                    "guide": defaults.get("guide") or row.get("description") or "",
                    "video_path": row.get("video_path") or f"/static/videos/{key}.mp4",
                    "is_today": defaults.get("is_today", False),
                    "analysis_supported": supported,
                    "status_label": status_label,
                    "support_message": None
                    if supported
                    else f"{status_label}: 이 운동 분석은 추후 지원 예정입니다.",
                }
            )
        if not any(exercise["key"] == "rom_shoulder" for exercise in exercises):
            exercises.insert(1, self._default_exercise_payload("rom_shoulder"))
        return exercises

    def _get_device_row(self, device_id):
        return self.database.query_one(
            """
            SELECT
                mirror_id,
                device_name,
                pairing_code,
                pairing_status,
                paired_user_id,
                created_at,
                updated_at
            FROM MirrorDevices
            WHERE mirror_id = ?
            """,
            [device_id],
        )

    def _create_exercise_record_db(self, record):
        self._ensure_known_exercise_db(record["exercise_key"])
        started_at = self._parse_datetime(record.get("started_at"))
        ended_at = self._parse_datetime(record.get("ended_at"))
        accuracy_avg = record.get("accuracy_avg")
        if accuracy_avg is not None:
            accuracy_avg = round(float(accuracy_avg), 2)

        saved = self.database.execute_returning_one(
            """
            INSERT INTO ExerciseRecords (
                user_id,
                exercise_key,
                accuracy_avg,
                feedback_summary,
                started_at,
                ended_at
            )
            OUTPUT
                INSERTED.record_id,
                INSERTED.user_id,
                INSERTED.exercise_key,
                INSERTED.accuracy_avg,
                INSERTED.feedback_summary,
                INSERTED.started_at,
                INSERTED.ended_at
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                record["user_id"],
                record["exercise_key"],
                accuracy_avg,
                (record.get("feedback_summary") or "")[:1000],
                started_at,
                ended_at,
            ],
        )
        return self._format_exercise_record(saved)

    def _list_exercise_records_db(self, user_id):
        rows = self.database.query_all(
            """
            SELECT
                record_id,
                user_id,
                exercise_key,
                accuracy_avg,
                feedback_summary,
                started_at,
                ended_at
            FROM ExerciseRecords
            WHERE user_id = ?
            ORDER BY started_at DESC, record_id DESC
            """,
            [user_id],
        )
        return [self._format_exercise_record(row) for row in rows]

    def _create_health_alert_if_needed_db(self, user_id, _health_check, candidate):
        source_rom_record_id = candidate.get("source_rom_record_id")
        source_exercise_record_ids = (
            candidate.get("source_exercise_record_ids") or "[]"
        )

        conn = self.database.connect()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT TOP 1
                    alert_id,
                    user_id,
                    alert_type,
                    severity,
                    title,
                    message,
                    overall_status,
                    source_rom_record_id,
                    source_exercise_record_ids,
                    is_read,
                    created_at
                FROM HealthAlerts WITH (UPDLOCK, HOLDLOCK)
                WHERE user_id = ?
                    AND overall_status = ?
                    AND (
                        source_rom_record_id = ?
                        OR (source_rom_record_id IS NULL AND ? IS NULL)
                    )
                    AND source_exercise_record_ids = ?
                ORDER BY created_at DESC, alert_id DESC
                """,
                user_id,
                candidate["overall_status"],
                source_rom_record_id,
                source_rom_record_id,
                source_exercise_record_ids,
            )
            existing = self._cursor_row_to_dict(cursor, cursor.fetchone())
            if existing:
                conn.commit()
                return {
                    "created": False,
                    "reason": "duplicate",
                    "alert": self._format_health_alert(existing),
                }

            cursor.execute(
                """
                INSERT INTO HealthAlerts (
                    user_id,
                    alert_type,
                    severity,
                    title,
                    message,
                    overall_status,
                    source_rom_record_id,
                    source_exercise_record_ids
                )
                OUTPUT
                    INSERTED.alert_id,
                    INSERTED.user_id,
                    INSERTED.alert_type,
                    INSERTED.severity,
                    INSERTED.title,
                    INSERTED.message,
                    INSERTED.overall_status,
                    INSERTED.source_rom_record_id,
                    INSERTED.source_exercise_record_ids,
                    INSERTED.is_read,
                    INSERTED.created_at
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                user_id,
                candidate["alert_type"],
                candidate["severity"],
                candidate["title"],
                candidate["message"],
                candidate["overall_status"],
                source_rom_record_id,
                source_exercise_record_ids,
            )
            saved = self._cursor_row_to_dict(cursor, cursor.fetchone())
            conn.commit()
            return {
                "created": True,
                "alert": self._format_health_alert(saved),
            }
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _list_guardian_alerts_db(self, guardian_id):
        rows = self.database.query_all(
            """
            SELECT
                alert.alert_id,
                alert.user_id,
                user_profile.name AS user_name,
                alert.alert_type,
                alert.severity,
                alert.title,
                alert.message,
                alert.overall_status,
                alert.source_rom_record_id,
                alert.source_exercise_record_ids,
                alert.is_read,
                alert.created_at
            FROM HealthAlerts AS alert
            INNER JOIN GuardianUserLinks AS link
                ON link.user_id = alert.user_id
            INNER JOIN ElderlyUsers AS user_profile
                ON user_profile.user_id = alert.user_id
            WHERE link.guardian_id = ?
            ORDER BY alert.created_at DESC, alert.alert_id DESC
            """,
            [guardian_id],
        )
        return [self._format_health_alert(row) for row in rows]

    def _mark_guardian_alert_read_db(self, guardian_id, alert_id):
        conn = self.database.connect()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT
                    alert.alert_id,
                    alert.user_id,
                    user_profile.name AS user_name,
                    alert.alert_type,
                    alert.severity,
                    alert.title,
                    alert.message,
                    alert.overall_status,
                    alert.source_rom_record_id,
                    alert.source_exercise_record_ids,
                    alert.is_read,
                    alert.created_at
                FROM HealthAlerts AS alert WITH (UPDLOCK, ROWLOCK)
                INNER JOIN GuardianUserLinks AS link
                    ON link.user_id = alert.user_id
                INNER JOIN ElderlyUsers AS user_profile
                    ON user_profile.user_id = alert.user_id
                WHERE link.guardian_id = ?
                    AND alert.alert_id = ?
                """,
                guardian_id,
                alert_id,
            )
            alert = self._cursor_row_to_dict(cursor, cursor.fetchone())
            if not alert:
                raise HealthAlertNotFound("health alert not found")

            cursor.execute(
                """
                UPDATE HealthAlerts
                SET is_read = 1
                WHERE alert_id = ?
                """,
                alert_id,
            )
            conn.commit()
            alert["is_read"] = True
            return self._format_health_alert(alert)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _create_guardian_account_db(self, guardian_id, login_id, password_hash, name):
        existing = self.database.query_one(
            """
            SELECT guardian_id
            FROM GuardianAccounts
            WHERE login_id = ?
            """,
            [login_id],
        )
        if existing:
            raise GuardianAlreadyExists(login_id)

        row = self.database.execute_returning_one(
            """
            INSERT INTO GuardianAccounts (
                guardian_id,
                login_id,
                password_hash,
                name,
                created_at,
                updated_at
            )
            OUTPUT
                INSERTED.guardian_id,
                INSERTED.login_id,
                INSERTED.name,
                INSERTED.created_at,
                INSERTED.updated_at
            VALUES (?, ?, ?, ?, SYSUTCDATETIME(), SYSUTCDATETIME())
            """,
            [guardian_id, login_id, password_hash, name],
        )
        return self._format_guardian(row)

    def _authenticate_guardian_db(self, login_id, password):
        row = self.database.query_one(
            """
            SELECT
                guardian_id,
                login_id,
                password_hash,
                name,
                created_at,
                updated_at
            FROM GuardianAccounts
            WHERE login_id = ?
            """,
            [login_id],
        )
        if not row or not check_password_hash(row["password_hash"], password):
            return None
        return self._format_guardian(row)

    def _list_guardian_users_db(self, guardian_id):
        rows = self.database.query_all(
            """
            SELECT
                u.user_id,
                u.name,
                u.birth_year,
                u.gender,
                u.birth_date,
                u.height_cm,
                u.weight_kg,
                u.health_condition,
                u.memo,
                u.created_at
            FROM GuardianUserLinks AS link
            INNER JOIN ElderlyUsers AS u
                ON u.user_id = link.user_id
            WHERE link.guardian_id = ?
            ORDER BY link.created_at ASC, u.created_at ASC, u.user_id ASC
            """,
            [guardian_id],
        )
        return [self._format_user(row) for row in rows]

    def _create_guardian_user_db(self, guardian_id, user_payload):
        name = (user_payload.get("name") or "").strip()
        if not name:
            raise UserValidationError("name is required")

        conn = self.database.connect()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT guardian_id
                FROM GuardianAccounts
                WHERE guardian_id = ?
                """,
                guardian_id,
            )
            if not cursor.fetchone():
                raise GuardianNotFound(guardian_id)

            user_id = self._generate_unique_user_id_db(cursor)
            cursor.execute(
                """
                INSERT INTO ElderlyUsers (
                    user_id,
                    name,
                    birth_year,
                    gender,
                    birth_date,
                    height_cm,
                    weight_kg,
                    health_condition,
                    memo,
                    created_at
                )
                OUTPUT
                    INSERTED.user_id,
                    INSERTED.name,
                    INSERTED.birth_year,
                    INSERTED.gender,
                    INSERTED.birth_date,
                    INSERTED.height_cm,
                    INSERTED.weight_kg,
                    INSERTED.health_condition,
                    INSERTED.memo,
                    INSERTED.created_at
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, SYSUTCDATETIME())
                """,
                user_id,
                name,
                user_payload.get("birth_year"),
                user_payload.get("gender"),
                user_payload.get("birth_date"),
                user_payload.get("height_cm"),
                user_payload.get("weight_kg"),
                user_payload.get("health_condition"),
                user_payload.get("memo"),
            )
            saved = self._cursor_row_to_dict(cursor, cursor.fetchone())

            cursor.execute(
                """
                INSERT INTO GuardianUserLinks (guardian_id, user_id, created_at)
                VALUES (?, ?, SYSUTCDATETIME())
                """,
                guardian_id,
                user_id,
            )
            conn.commit()
            return self._format_user(saved)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _update_guardian_user_db(self, guardian_id, user_id, updates):
        updates = dict(updates)
        allowed_fields = {
            "name",
            "gender",
            "birth_date",
            "birth_year",
            "height_cm",
            "weight_kg",
            "health_condition",
            "memo",
        }
        if not updates or any(field not in allowed_fields for field in updates):
            raise UserValidationError("invalid user profile")
        if "name" in updates and not (updates.get("name") or "").strip():
            raise UserValidationError("name is required")

        if updates.get("birth_date") is not None:
            birth_date_year = self._birth_date_year(updates["birth_date"])
            if updates.get("birth_year") not in (None, birth_date_year):
                raise UserValidationError("birth_year must match birth_date year")
            updates["birth_year"] = birth_date_year

        conn = self.database.connect()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT guardian_id
                FROM GuardianAccounts
                WHERE guardian_id = ?
                """,
                guardian_id,
            )
            if not cursor.fetchone():
                raise GuardianNotFound(guardian_id)

            cursor.execute(
                """
                SELECT
                    u.user_id,
                    u.birth_date
                FROM GuardianUserLinks AS link
                INNER JOIN ElderlyUsers AS u
                    ON u.user_id = link.user_id
                WHERE link.guardian_id = ?
                    AND link.user_id = ?
                """,
                guardian_id,
                user_id,
            )
            current = self._cursor_row_to_dict(cursor, cursor.fetchone())
            if not current:
                raise GuardianUserLinkNotFound(user_id)

            if "birth_year" in updates and "birth_date" not in updates:
                existing_birth_year = self._birth_date_year(current.get("birth_date"))
                if existing_birth_year is not None and updates["birth_year"] != existing_birth_year:
                    raise UserValidationError("birth_year must match existing birth_date year")

            columns = list(updates)
            set_clause = ", ".join(f"{column} = ?" for column in columns)
            cursor.execute(
                f"""
                UPDATE ElderlyUsers
                SET {set_clause}
                WHERE user_id = ?
                """,
                *[updates[column] for column in columns],
                user_id,
            )
            cursor.execute(
                """
                SELECT
                    user_id,
                    name,
                    birth_year,
                    gender,
                    birth_date,
                    height_cm,
                    weight_kg,
                    health_condition,
                    memo,
                    created_at
                FROM ElderlyUsers
                WHERE user_id = ?
                """,
                user_id,
            )
            saved = self._cursor_row_to_dict(cursor, cursor.fetchone())
            conn.commit()
            return self._format_user(saved)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _unlink_guardian_user_db(self, guardian_id, user_id):
        conn = self.database.connect()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT guardian_id
                FROM GuardianAccounts
                WHERE guardian_id = ?
                """,
                guardian_id,
            )
            if not cursor.fetchone():
                raise GuardianNotFound(guardian_id)

            cursor.execute(
                """
                SELECT 1
                FROM GuardianUserLinks
                WHERE guardian_id = ?
                    AND user_id = ?
                """,
                guardian_id,
                user_id,
            )
            if not cursor.fetchone():
                raise GuardianUserLinkNotFound(user_id)

            cursor.execute(
                """
                DELETE FROM GuardianUserLinks
                WHERE guardian_id = ?
                    AND user_id = ?
                """,
                guardian_id,
                user_id,
            )
            conn.commit()
            return {
                "guardian_id": guardian_id,
                "user_id": user_id,
                "unlinked": True,
                "deleted_user": False,
                "deleted_exercise_records": False,
            }
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _create_guardian_user_link_db(self, guardian_id, user_id):
        guardian = self.database.query_one(
            """
            SELECT guardian_id
            FROM GuardianAccounts
            WHERE guardian_id = ?
            """,
            [guardian_id],
        )
        user = self.database.query_one(
            """
            SELECT user_id
            FROM ElderlyUsers
            WHERE user_id = ?
            """,
            [user_id],
        )
        if not guardian or not user:
            return None

        self.database.execute(
            """
            IF NOT EXISTS (
                SELECT 1
                FROM GuardianUserLinks
                WHERE guardian_id = ? AND user_id = ?
            )
            BEGIN
                INSERT INTO GuardianUserLinks (guardian_id, user_id, created_at)
                VALUES (?, ?, SYSUTCDATETIME())
            END
            """,
            [guardian_id, user_id, guardian_id, user_id],
        )
        return {"guardian_id": guardian_id, "user_id": user_id}

    def _cursor_row_to_dict(self, cursor, row):
        if not row:
            return None
        columns = [column[0] for column in cursor.description]
        return dict(zip(columns, row))

    def _generate_unique_user_id_db(self, cursor):
        for _ in range(20):
            user_id = f"user-{uuid4().hex}"
            cursor.execute(
                """
                SELECT 1
                FROM ElderlyUsers
                WHERE user_id = ?
                """,
                user_id,
            )
            if not cursor.fetchone():
                return user_id
        raise UserValidationError("could not generate unique user_id")

    def _birth_date_year(self, value):
        if value is None:
            return None
        if isinstance(value, (date, datetime)):
            return value.year
        return date.fromisoformat(str(value)).year

    def _ensure_known_exercise_db(self, exercise_key):
        defaults = EXERCISE_UI_DEFAULTS.get(exercise_key)
        if not defaults or "title" not in defaults:
            return

        self.database.execute(
            """
            IF NOT EXISTS (SELECT 1 FROM Exercises WHERE exercise_key = ?)
            BEGIN
                INSERT INTO Exercises (
                    exercise_key,
                    title,
                    category,
                    description,
                    video_path,
                    is_supported,
                    status_label
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
            END
            """,
            [
                exercise_key,
                exercise_key,
                defaults["title"],
                defaults["category"],
                defaults["description"],
                defaults["video_path"],
                1 if defaults["is_supported"] else 0,
                defaults["status_label"],
            ],
        )

    def _default_exercise_payload(self, exercise_key):
        defaults = EXERCISE_UI_DEFAULTS[exercise_key]
        supported = bool(defaults.get("is_supported", False))
        return {
            "key": exercise_key,
            "name": defaults.get("title", exercise_key),
            "category": defaults.get("category", "질환 예방 운동"),
            "part": defaults.get("part", "전신"),
            "target": defaults.get("target", 1),
            "duration": defaults.get("duration", "준비 중"),
            "angle": defaults.get("angle", 0),
            "description": defaults.get("description", ""),
            "guide": defaults.get("guide", defaults.get("description", "")),
            "video_path": defaults.get("video_path", f"/static/videos/{exercise_key}.mp4"),
            "is_today": defaults.get("is_today", False),
            "analysis_supported": supported,
            "status_label": defaults.get(
                "status_label", "분석 가능" if supported else "준비 중"
            ),
            "support_message": None
            if supported
            else "이 운동 분석은 추후 지원 예정입니다.",
        }

    def _pairing_remaining_seconds(self, updated_at):
        if not isinstance(updated_at, datetime):
            return PAIRING_SECONDS
        elapsed = int((datetime.utcnow() - updated_at).total_seconds())
        return max(0, PAIRING_SECONDS - elapsed)

    def _parse_datetime(self, value):
        if isinstance(value, datetime):
            parsed = value
        elif value:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        else:
            parsed = datetime.utcnow()

        if parsed.tzinfo:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed

    def _format_health_alert(self, row):
        if not row:
            return None

        source_rom_record_id = row.get("source_rom_record_id")
        if source_rom_record_id is not None:
            source_rom_record_id = int(source_rom_record_id)

        return {
            "alert_id": int(row["alert_id"]),
            "user_id": row["user_id"],
            "user_name": row.get("user_name"),
            "alert_type": row.get("alert_type") or "shoulder_function",
            "severity": row["severity"],
            "title": row["title"],
            "message": row["message"],
            "overall_status": row["overall_status"],
            "source_rom_record_id": source_rom_record_id,
            "source_exercise_record_ids": decode_source_exercise_record_ids(
                row.get("source_exercise_record_ids")
            ),
            "is_read": bool(row.get("is_read")),
            "created_at": self._format_datetime(row.get("created_at")),
        }

    def _format_exercise_record(self, row):
        if not row:
            return None

        accuracy = row.get("accuracy_avg")
        if isinstance(accuracy, Decimal):
            accuracy = float(accuracy)

        return {
            "record_id": int(row["record_id"]),
            "user_id": row["user_id"],
            "exercise_key": row["exercise_key"],
            "accuracy_avg": accuracy,
            "feedback_summary": row.get("feedback_summary") or "",
            "started_at": self._format_datetime(row.get("started_at")),
            "ended_at": self._format_datetime(row.get("ended_at")),
        }

    def _format_user(self, row):
        user_id = row.get("user_id") or row.get("id")
        return {
            "id": user_id,
            "user_id": user_id,
            "name": row["name"],
            "birth_year": row.get("birth_year"),
            "gender": row.get("gender"),
            "birth_date": self._format_date(row.get("birth_date")),
            "height_cm": self._format_decimal(row.get("height_cm")),
            "weight_kg": self._format_decimal(row.get("weight_kg")),
            "health_condition": row.get("health_condition"),
            "program": "질환 예방 운동",
            "goal": row.get("memo") or "개인 맞춤 질환 예방",
            "memo": row.get("memo") or "",
            "created_at": self._format_datetime(row.get("created_at")),
        }

    def _format_guardian(self, row):
        if not row:
            return None

        return {
            "guardian_id": row["guardian_id"],
            "login_id": row["login_id"],
            "name": row["name"],
            "created_at": self._format_datetime(row.get("created_at")),
            "updated_at": self._format_datetime(row.get("updated_at")),
        }

    def _format_device(self, row):
        if not row:
            return None

        return {
            "mirror_id": row["mirror_id"],
            "device_name": row["device_name"],
            "pairing_status": row.get("pairing_status") or "waiting",
            "paired_user_id": row.get("paired_user_id"),
        }

    def _format_datetime(self, value):
        if isinstance(value, datetime):
            if value.tzinfo:
                value = value.astimezone(timezone.utc).replace(tzinfo=None)
            return f"{value.isoformat()}Z"
        return value

    def _format_date(self, value):
        if isinstance(value, (date, datetime)):
            return value.isoformat()[:10]
        return value

    def _format_decimal(self, value):
        if isinstance(value, Decimal):
            return float(value)
        return value


data_store = SmartMirrorDataStore()
