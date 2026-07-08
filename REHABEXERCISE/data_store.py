import os
import random
import time
from datetime import datetime

from db import DatabaseUnavailable, MSSQLDatabase, load_env_file
import mock_data


load_env_file()

PAIRING_SECONDS = int(os.getenv("PAIRING_CODE_TTL_SECONDS", "600"))
CODE_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
DEFAULT_MIRROR_ID = os.getenv(
    "DB_MIRROR_ID", os.getenv("MSSQL_MIRROR_ID", "mirror-demo-001")
)

EXERCISE_UI_DEFAULTS = {
    "shoulder": {
        "part": "상체",
        "target": 3,
        "duration": "약 1분",
        "angle": 155,
        "guide": "가이드 영상에 맞춰 1단계 왼쪽, 2단계 정면, 3단계 오른쪽 순서로 움직입니다.",
        "is_today": True,
    },
    "knee": {
        "part": "하체",
        "target": 15,
        "duration": "약 7분",
        "angle": 70,
        "guide": "의자나 벽을 가까이 두고 통증이 없는 범위에서 진행하세요.",
        "is_today": True,
    },
    "flexibility": {
        "part": "상체",
        "target": 12,
        "duration": "약 6분",
        "angle": 75,
        "guide": "반동을 주지 말고 편안하게 호흡하며 움직이세요.",
        "is_today": True,
    },
    "balance": {
        "part": "전신",
        "target": 12,
        "duration": "약 7분",
        "angle": 65,
        "guide": "필요하면 보호자나 벽을 가까이 두고 진행하세요.",
        "is_today": False,
    },
}


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

    def _run(self, db_func, fallback_func, *args):
        if not self.database.is_configured():
            return self._fallback(
                DatabaseUnavailable("MSSQL is not enabled or configured"),
                fallback_func,
                *args,
            )

        try:
            value = db_func(*args)
            if value is None:
                return self._fallback(
                    DatabaseUnavailable("MSSQL returned no rows"), fallback_func, *args
                )
            self._using_mssql()
            return value
        except Exception as exc:
            return self._fallback(exc, fallback_func, *args)

    def get_current_device(self):
        return self._run(self._get_current_device_db, mock_data.get_current_device)

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

    def list_users(self, device_id=None):
        resolved_device_id = device_id or DEFAULT_MIRROR_ID
        return self._run(
            self._list_users_db, mock_data.list_users, resolved_device_id
        )

    def list_exercises(self):
        return self._run(self._list_exercises_db, mock_data.list_exercises)

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

    def _list_users_db(self, device_id):
        rows = self.database.query_all(
            """
            SELECT user_id, name, birth_year, memo, created_at
            FROM ElderlyUsers
            ORDER BY created_at ASC, user_id ASC
            """
        )
        if not rows:
            return None

        return [
            {
                "id": row["user_id"],
                "name": row["name"],
                "birth_year": row.get("birth_year"),
                "program": "재활 운동",
                "goal": row.get("memo") or "개인 맞춤 재활",
                "memo": row.get("memo") or "",
            }
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
                    WHEN 'knee' THEN 2
                    WHEN 'flexibility' THEN 3
                    WHEN 'balance' THEN 4
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
                    "category": row.get("category") or "재활 운동",
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

    def _pairing_remaining_seconds(self, updated_at):
        if not isinstance(updated_at, datetime):
            return PAIRING_SECONDS
        elapsed = int((datetime.utcnow() - updated_at).total_seconds())
        return max(0, PAIRING_SECONDS - elapsed)


data_store = SmartMirrorDataStore()
