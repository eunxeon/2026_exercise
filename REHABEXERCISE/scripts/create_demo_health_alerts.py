import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from db import MSSQLDatabase  # noqa: E402


GUARDIAN_ID = "guardian-demo-001"
USER_ID = "user-1"
EXPECTED_USER_NAME = "김영희"
ALERT_TYPE = "health_check"
SOURCE_EXERCISE_RECORD_IDS = "[]"

DEMO_ALERTS = [
    {
        "name": "caution",
        "severity": "caution",
        "overall_status": "caution",
        "title": "운동 기능 상태를 확인해주세요",
        "message": (
            "최근 어깨 관절 가동 범위가 평소보다 낮게 측정되어 주의가 필요합니다. "
            "지속적으로 상태를 확인해주세요."
        ),
    },
    {
        "name": "warning",
        "severity": "warning",
        "overall_status": "check_required",
        "title": "운동 기능 점검이 필요합니다",
        "message": (
            "최근 운동 수행 정확도와 관절 가동 범위에서 기능 저하 징후가 확인되었습니다. "
            "상태를 지속적으로 확인해주세요."
        ),
    },
]

FORBIDDEN_TERMS = (
    "오십견",
    "관절염",
    "뇌졸중",
    "질병 진단",
    "장애 판정",
    "질병 확정",
)


def cursor_row_to_dict(cursor, row):
    if not row:
        return None
    columns = [column[0] for column in cursor.description]
    return dict(zip(columns, row))


def format_datetime(value):
    if hasattr(value, "isoformat"):
        return f"{value.isoformat()}Z"
    return str(value)


def normalize_alert(row):
    if not row:
        return None
    return {
        "alert_id": int(row["alert_id"]),
        "user_id": row["user_id"],
        "user_name": row.get("user_name"),
        "alert_type": row["alert_type"],
        "severity": row["severity"],
        "title": row["title"],
        "message": row["message"],
        "overall_status": row["overall_status"],
        "source_rom_record_id": row["source_rom_record_id"],
        "source_exercise_record_ids": row["source_exercise_record_ids"],
        "is_read": bool(row["is_read"]),
        "created_at": format_datetime(row["created_at"]),
    }


def validate_demo_alert_text():
    for alert in DEMO_ALERTS:
        text = f"{alert['title']} {alert['message']}"
        for term in FORBIDDEN_TERMS:
            if term in text:
                raise SystemExit(f"Forbidden alert term found: {term}")


def fetch_guardian_link(cursor):
    cursor.execute(
        """
        SELECT TOP 1
            link.guardian_id,
            link.user_id,
            user_profile.name AS user_name
        FROM GuardianUserLinks AS link
        INNER JOIN ElderlyUsers AS user_profile
            ON user_profile.user_id = link.user_id
        WHERE link.guardian_id = ?
            AND link.user_id = ?
        """,
        GUARDIAN_ID,
        USER_ID,
    )
    return cursor_row_to_dict(cursor, cursor.fetchone())


def count_exercise_records(cursor):
    cursor.execute(
        """
        SELECT COUNT(*) AS record_count
        FROM ExerciseRecords
        WHERE user_id = ?
        """,
        USER_ID,
    )
    row = cursor_row_to_dict(cursor, cursor.fetchone())
    return int(row["record_count"])


def delete_existing_demo_alerts(cursor):
    deleted_alerts = []
    for alert in DEMO_ALERTS:
        cursor.execute(
            """
            DELETE FROM HealthAlerts
            OUTPUT
                DELETED.alert_id,
                DELETED.user_id,
                CAST(NULL AS NVARCHAR(80)) AS user_name,
                DELETED.alert_type,
                DELETED.severity,
                DELETED.title,
                DELETED.message,
                DELETED.overall_status,
                DELETED.source_rom_record_id,
                DELETED.source_exercise_record_ids,
                DELETED.is_read,
                DELETED.created_at
            WHERE user_id = ?
                AND alert_type = ?
                AND severity = ?
                AND title = ?
                AND message = ?
                AND overall_status = ?
                AND source_rom_record_id IS NULL
                AND source_exercise_record_ids = ?
            """,
            USER_ID,
            ALERT_TYPE,
            alert["severity"],
            alert["title"],
            alert["message"],
            alert["overall_status"],
            SOURCE_EXERCISE_RECORD_IDS,
        )
        deleted_alerts.extend(
            normalize_alert(cursor_row_to_dict(cursor, row)) for row in cursor.fetchall()
        )
    return deleted_alerts


def insert_demo_alert(cursor, alert, created_at):
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
            source_exercise_record_ids,
            is_read,
            created_at
        )
        OUTPUT
            INSERTED.alert_id,
            INSERTED.user_id,
            CAST(NULL AS NVARCHAR(80)) AS user_name,
            INSERTED.alert_type,
            INSERTED.severity,
            INSERTED.title,
            INSERTED.message,
            INSERTED.overall_status,
            INSERTED.source_rom_record_id,
            INSERTED.source_exercise_record_ids,
            INSERTED.is_read,
            INSERTED.created_at
        VALUES (?, ?, ?, ?, ?, ?, NULL, ?, 0, ?)
        """,
        USER_ID,
        ALERT_TYPE,
        alert["severity"],
        alert["title"],
        alert["message"],
        alert["overall_status"],
        SOURCE_EXERCISE_RECORD_IDS,
        created_at,
    )
    return cursor_row_to_dict(cursor, cursor.fetchone())


def fetch_demo_alerts(cursor):
    titles = [alert["title"] for alert in DEMO_ALERTS]
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
        FROM HealthAlerts AS alert
        INNER JOIN ElderlyUsers AS user_profile
            ON user_profile.user_id = alert.user_id
        WHERE alert.user_id = ?
            AND alert.alert_type = ?
            AND alert.title IN (?, ?)
        ORDER BY alert.created_at ASC, alert.alert_id ASC
        """,
        USER_ID,
        ALERT_TYPE,
        titles[0],
        titles[1],
    )
    return [cursor_row_to_dict(cursor, row) for row in cursor.fetchall()]


def main():
    validate_demo_alert_text()

    database = MSSQLDatabase()
    if not database.is_configured():
        raise SystemExit("MSSQL is not enabled or configured; aborting without changes.")

    conn = database.connect()
    try:
        cursor = conn.cursor()
        guardian_link = fetch_guardian_link(cursor)
        if not guardian_link:
            raise SystemExit(
                f"{GUARDIAN_ID} is not linked to {USER_ID}; aborting without changes."
            )
        if guardian_link["user_name"] != EXPECTED_USER_NAME:
            raise SystemExit(
                f"{USER_ID} name is {guardian_link['user_name']!r}, expected {EXPECTED_USER_NAME!r}; aborting without changes."
            )

        exercise_records_before = count_exercise_records(cursor)
        deleted_alerts = delete_existing_demo_alerts(cursor)

        now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
        for offset_seconds, alert in enumerate(DEMO_ALERTS):
            insert_demo_alert(
                cursor,
                alert,
                now_utc + timedelta(seconds=offset_seconds),
            )

        exercise_records_after = count_exercise_records(cursor)
        if exercise_records_after != exercise_records_before:
            conn.rollback()
            raise SystemExit(
                "ExerciseRecords count changed unexpectedly; transaction rolled back."
            )

        demo_alerts = fetch_demo_alerts(cursor)
        if len(demo_alerts) != len(DEMO_ALERTS):
            conn.rollback()
            raise SystemExit(
                f"Expected {len(DEMO_ALERTS)} demo alerts, found {len(demo_alerts)}; transaction rolled back."
            )

        conn.commit()
        print(
            json.dumps(
                {
                    "success": True,
                    "action": "recreated_demo_health_alerts",
                    "guardian_link": guardian_link,
                    "deleted_existing_demo_alerts": deleted_alerts,
                    "exercise_records_before": exercise_records_before,
                    "exercise_records_after": exercise_records_after,
                    "alerts": [normalize_alert(alert) for alert in demo_alerts],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
