import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from db import MSSQLDatabase  # noqa: E402


USER_ID = "user-1"
ALERT_TYPE = "health_check"
TITLE = "테스트 운동 기능 알림"
MESSAGE = "Android 알림 표시 및 읽음 처리를 확인하기 위한 테스트 알림입니다."
OVERALL_STATUS = "caution"


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


def delete_test_alert(cursor, alert_id):
    cursor.execute(
        """
        DELETE FROM HealthAlerts
        OUTPUT
            DELETED.alert_id,
            DELETED.user_id,
            DELETED.alert_type,
            DELETED.severity,
            DELETED.title,
            DELETED.message,
            DELETED.overall_status,
            DELETED.source_rom_record_id,
            DELETED.source_exercise_record_ids,
            DELETED.is_read,
            DELETED.created_at
        WHERE alert_id = ?
            AND user_id = ?
            AND alert_type = ?
            AND title = ?
            AND message = ?
            AND overall_status = ?
        """,
        alert_id,
        USER_ID,
        ALERT_TYPE,
        TITLE,
        MESSAGE,
        OVERALL_STATUS,
    )
    return cursor_row_to_dict(cursor, cursor.fetchone())


def parse_args():
    parser = argparse.ArgumentParser(
        description="Delete exactly one Android HealthAlerts test row."
    )
    parser.add_argument(
        "--alert-id",
        required=True,
        type=int,
        help="The test HealthAlerts.alert_id returned by create_test_health_alert.py.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    database = MSSQLDatabase()
    if not database.is_configured():
        raise SystemExit("MSSQL is not enabled or configured; aborting without changes.")

    conn = database.connect()
    try:
        cursor = conn.cursor()
        exercise_records_before = count_exercise_records(cursor)
        deleted_alert = delete_test_alert(cursor, args.alert_id)
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
                    "deleted": deleted_alert is not None,
                    "exercise_records_before": exercise_records_before,
                    "exercise_records_after": exercise_records_after,
                    "deleted_alert": normalize_alert(deleted_alert),
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
