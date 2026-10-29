import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from db import MSSQLDatabase  # noqa: E402


USER_ID = "user-1"
ALERT_TYPE = "health_check"
SOURCE_EXERCISE_RECORD_IDS = "[]"

EXPECTED_ALERTS = {
    "caution": {
        "severity": "caution",
        "overall_status": "caution",
        "title": "운동 기능 상태를 확인해주세요",
        "message": (
            "최근 어깨 관절 가동 범위가 평소보다 낮게 측정되어 주의가 필요합니다. "
            "지속적으로 상태를 확인해주세요."
        ),
    },
    "warning": {
        "severity": "warning",
        "overall_status": "check_required",
        "title": "운동 기능 점검이 필요합니다",
        "message": (
            "최근 운동 수행 정확도와 관절 가동 범위에서 기능 저하 징후가 확인되었습니다. "
            "상태를 지속적으로 확인해주세요."
        ),
    },
}


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


def fetch_expected_alert(cursor, alert_id, expected):
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
        WHERE alert_id = ?
            AND user_id = ?
            AND alert_type = ?
            AND severity = ?
            AND title = ?
            AND message = ?
            AND overall_status = ?
            AND source_rom_record_id IS NULL
            AND source_exercise_record_ids = ?
        """,
        alert_id,
        USER_ID,
        ALERT_TYPE,
        expected["severity"],
        expected["title"],
        expected["message"],
        expected["overall_status"],
        SOURCE_EXERCISE_RECORD_IDS,
    )
    return cursor_row_to_dict(cursor, cursor.fetchone())


def delete_expected_alert(cursor, alert_id, expected):
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
            AND severity = ?
            AND title = ?
            AND message = ?
            AND overall_status = ?
            AND source_rom_record_id IS NULL
            AND source_exercise_record_ids = ?
        """,
        alert_id,
        USER_ID,
        ALERT_TYPE,
        expected["severity"],
        expected["title"],
        expected["message"],
        expected["overall_status"],
        SOURCE_EXERCISE_RECORD_IDS,
    )
    return cursor_row_to_dict(cursor, cursor.fetchone())


def parse_args():
    parser = argparse.ArgumentParser(
        description="Delete only the two Android demo HealthAlerts rows."
    )
    parser.add_argument(
        "--caution-alert-id",
        required=True,
        type=int,
        help="HealthAlerts.alert_id for '운동 기능 상태를 확인해주세요'.",
    )
    parser.add_argument(
        "--warning-alert-id",
        required=True,
        type=int,
        help="HealthAlerts.alert_id for '운동 기능 점검이 필요합니다'.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    alert_ids = {
        "caution": args.caution_alert_id,
        "warning": args.warning_alert_id,
    }
    if alert_ids["caution"] == alert_ids["warning"]:
        raise SystemExit("caution and warning alert IDs must be different.")

    database = MSSQLDatabase()
    if not database.is_configured():
        raise SystemExit("MSSQL is not enabled or configured; aborting without changes.")

    conn = database.connect()
    try:
        cursor = conn.cursor()
        exercise_records_before = count_exercise_records(cursor)

        matched_alerts = {}
        for name, alert_id in alert_ids.items():
            matched = fetch_expected_alert(cursor, alert_id, EXPECTED_ALERTS[name])
            if not matched:
                conn.rollback()
                raise SystemExit(
                    f"Alert {alert_id} did not match expected {name} demo alert; aborting without changes."
                )
            matched_alerts[name] = matched

        deleted_alerts = []
        for name, alert_id in alert_ids.items():
            deleted_alerts.append(
                delete_expected_alert(cursor, alert_id, EXPECTED_ALERTS[name])
            )

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
                    "deleted_alerts": [
                        normalize_alert(alert) for alert in deleted_alerts
                    ],
                    "exercise_records_before": exercise_records_before,
                    "exercise_records_after": exercise_records_after,
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
