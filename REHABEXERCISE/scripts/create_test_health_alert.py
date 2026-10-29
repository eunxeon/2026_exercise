import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from db import MSSQLDatabase  # noqa: E402


GUARDIAN_ID = "guardian-demo-001"
USER_ID = "user-1"
ALERT_TYPE = "health_check"
SEVERITY = "caution"
TITLE = "테스트 운동 기능 알림"
MESSAGE = "Android 알림 표시 및 읽음 처리를 확인하기 위한 테스트 알림입니다."
OVERALL_STATUS = "caution"
SOURCE_EXERCISE_RECORD_IDS = "[]"


def cursor_row_to_dict(cursor, row):
    if not row:
        return None
    columns = [column[0] for column in cursor.description]
    return dict(zip(columns, row))


def normalize_alert(row):
    if not row:
        return None
    return {
        "alert_id": row["alert_id"],
        "user_id": row["user_id"],
        "alert_type": row["alert_type"],
        "severity": row["severity"],
        "title": row["title"],
        "message": row["message"],
        "overall_status": row["overall_status"],
        "source_rom_record_id": row["source_rom_record_id"],
        "source_exercise_record_ids": row["source_exercise_record_ids"],
        "is_read": bool(row["is_read"]),
        "created_at": row["created_at"].isoformat()
        if hasattr(row["created_at"], "isoformat")
        else str(row["created_at"]),
    }


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


def fetch_matching_test_alerts(cursor):
    cursor.execute(
        """
        SELECT
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
            AND alert_type = ?
            AND title = ?
            AND message = ?
            AND overall_status = ?
        ORDER BY
            CASE WHEN is_read = 0 THEN 0 ELSE 1 END,
            created_at DESC,
            alert_id DESC
        """,
        USER_ID,
        ALERT_TYPE,
        TITLE,
        MESSAGE,
        OVERALL_STATUS,
    )
    return [cursor_row_to_dict(cursor, row) for row in cursor.fetchall()]


def fetch_alert_by_id(cursor, alert_id):
    cursor.execute(
        """
        SELECT
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
        FROM HealthAlerts
        WHERE alert_id = ?
        """,
        alert_id,
    )
    return cursor_row_to_dict(cursor, cursor.fetchone())


def delete_matching_test_alerts(cursor, *, keep_alert_id=None):
    sql = """
        DELETE FROM HealthAlerts
        OUTPUT DELETED.alert_id
        WHERE user_id = ?
            AND alert_type = ?
            AND title = ?
            AND message = ?
            AND overall_status = ?
    """
    params = [USER_ID, ALERT_TYPE, TITLE, MESSAGE, OVERALL_STATUS]
    if keep_alert_id is not None:
        sql += " AND alert_id <> ?"
        params.append(keep_alert_id)

    cursor.execute(sql, *params)
    return [int(row[0]) for row in cursor.fetchall()]


def insert_test_alert(cursor):
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
            INSERTED.alert_type,
            INSERTED.severity,
            INSERTED.title,
            INSERTED.message,
            INSERTED.overall_status,
            INSERTED.source_rom_record_id,
            INSERTED.source_exercise_record_ids,
            INSERTED.is_read,
            INSERTED.created_at
        VALUES (?, ?, ?, ?, ?, ?, NULL, ?, 0, SYSUTCDATETIME())
        """,
        USER_ID,
        ALERT_TYPE,
        SEVERITY,
        TITLE,
        MESSAGE,
        OVERALL_STATUS,
        SOURCE_EXERCISE_RECORD_IDS,
    )
    return cursor_row_to_dict(cursor, cursor.fetchone())


def main():
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

        exercise_records_before = count_exercise_records(cursor)
        matching_alerts = fetch_matching_test_alerts(cursor)
        existing_unread = next(
            (alert for alert in matching_alerts if not bool(alert["is_read"])),
            None,
        )

        if existing_unread:
            deleted_alert_ids = delete_matching_test_alerts(
                cursor,
                keep_alert_id=existing_unread["alert_id"],
            )
            alert = fetch_alert_by_id(cursor, existing_unread["alert_id"])
            action = "kept_existing_unread"
        else:
            deleted_alert_ids = delete_matching_test_alerts(cursor)
            alert = insert_test_alert(cursor)
            action = "created"

        exercise_records_after = count_exercise_records(cursor)
        if exercise_records_after != exercise_records_before:
            conn.rollback()
            raise SystemExit(
                "ExerciseRecords count changed unexpectedly; transaction rolled back."
            )

        conn.commit()
        print(
            json.dumps(
                {
                    "success": True,
                    "action": action,
                    "guardian_link": guardian_link,
                    "deleted_duplicate_test_alert_ids": deleted_alert_ids,
                    "exercise_records_before": exercise_records_before,
                    "exercise_records_after": exercise_records_after,
                    "alert": normalize_alert(alert),
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
