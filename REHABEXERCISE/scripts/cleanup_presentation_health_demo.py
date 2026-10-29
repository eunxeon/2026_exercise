import json
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from db import MSSQLDatabase  # noqa: E402
from health_check import build_shoulder_health_check  # noqa: E402


USER_ID = "user-1"
DEMO_MARKER = "[presentation-health-demo]"
TARGET_OVERALL_STATUS = "check_required"


def configure_stdout():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")


def cursor_row_to_dict(cursor, row):
    if not row:
        return None
    columns = [column[0] for column in cursor.description]
    return dict(zip(columns, row))


def to_jsonable(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        if value.tzinfo:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return f"{value.isoformat()}Z"
    return value


def normalize_record(row):
    if not row:
        return None
    return {
        "record_id": int(row["record_id"]),
        "user_id": row["user_id"],
        "exercise_key": row["exercise_key"],
        "accuracy_avg": to_jsonable(row.get("accuracy_avg")),
        "feedback_summary": row.get("feedback_summary") or "",
        "started_at": to_jsonable(row.get("started_at")),
        "ended_at": to_jsonable(row.get("ended_at")),
    }


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
        "source_rom_record_id": (
            int(row["source_rom_record_id"])
            if row.get("source_rom_record_id") is not None
            else None
        ),
        "source_exercise_record_ids": row["source_exercise_record_ids"],
        "is_read": bool(row["is_read"]),
        "created_at": to_jsonable(row.get("created_at")),
    }


def count_user_records(cursor):
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


def fetch_demo_records(cursor, *, lock=False):
    lock_clause = "WITH (UPDLOCK, HOLDLOCK)" if lock else ""
    cursor.execute(
        f"""
        SELECT
            record_id,
            user_id,
            exercise_key,
            accuracy_avg,
            feedback_summary,
            started_at,
            ended_at
        FROM ExerciseRecords {lock_clause}
        WHERE user_id = ?
            AND CHARINDEX(?, feedback_summary) > 0
        ORDER BY started_at ASC, ended_at ASC, record_id ASC
        """,
        USER_ID,
        DEMO_MARKER,
    )
    return [normalize_record(cursor_row_to_dict(cursor, row)) for row in cursor.fetchall()]


def demo_source_exercise_record_ids(records):
    shoulder_records = [
        record for record in records if record["exercise_key"] == "shoulder"
    ]
    shoulder_records.sort(
        key=lambda record: (
            str(record.get("started_at") or ""),
            str(record.get("ended_at") or ""),
            int(record["record_id"]),
        ),
        reverse=True,
    )
    return [record["record_id"] for record in shoulder_records]


def fetch_matching_demo_alerts(cursor, records):
    rom_ids = [
        record["record_id"]
        for record in records
        if record["exercise_key"] == "rom_shoulder"
    ]
    if len(rom_ids) != 1:
        return []

    source_exercise_ids = json.dumps(
        demo_source_exercise_record_ids(records),
        ensure_ascii=False,
        separators=(",", ":"),
    )
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
            AND severity = ?
            AND overall_status = ?
            AND source_rom_record_id = ?
            AND source_exercise_record_ids = ?
        ORDER BY created_at ASC, alert_id ASC
        """,
        USER_ID,
        "shoulder_function",
        "warning",
        TARGET_OVERALL_STATUS,
        rom_ids[0],
        source_exercise_ids,
    )
    return [cursor_row_to_dict(cursor, row) for row in cursor.fetchall()]


def delete_matching_demo_alerts(cursor, alerts):
    deleted = []
    for alert in alerts:
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
                AND overall_status = ?
                AND source_rom_record_id = ?
                AND source_exercise_record_ids = ?
            """,
            int(alert["alert_id"]),
            USER_ID,
            alert["alert_type"],
            alert["severity"],
            alert["overall_status"],
            alert["source_rom_record_id"],
            alert["source_exercise_record_ids"],
        )
        deleted.append(normalize_alert(cursor_row_to_dict(cursor, cursor.fetchone())))
    return deleted


def delete_demo_records(cursor, records):
    deleted = []
    for record in records:
        cursor.execute(
            """
            DELETE FROM ExerciseRecords
            OUTPUT
                DELETED.record_id,
                DELETED.user_id,
                DELETED.exercise_key,
                DELETED.accuracy_avg,
                DELETED.feedback_summary,
                DELETED.started_at,
                DELETED.ended_at
            WHERE record_id = ?
                AND user_id = ?
                AND CHARINDEX(?, feedback_summary) > 0
            """,
            int(record["record_id"]),
            USER_ID,
            DEMO_MARKER,
        )
        deleted.append(normalize_record(cursor_row_to_dict(cursor, cursor.fetchone())))
    return deleted


def fetch_all_user_records(database):
    rows = database.query_all(
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
        [USER_ID],
    )
    return [normalize_record(row) for row in rows]


def main():
    configure_stdout()

    database = MSSQLDatabase()
    if not database.is_configured():
        raise SystemExit("MSSQL is not enabled or configured; aborting without changes.")

    conn = database.connect()
    try:
        cursor = conn.cursor()
        exercise_records_before = count_user_records(cursor)
        demo_records = fetch_demo_records(cursor, lock=True)

        if demo_records:
            matching_alerts = fetch_matching_demo_alerts(cursor, demo_records)
            deleted_alerts = delete_matching_demo_alerts(cursor, matching_alerts)
            deleted_records = delete_demo_records(cursor, demo_records)
        else:
            matching_alerts = []
            deleted_alerts = []
            deleted_records = []

        exercise_records_after = count_user_records(cursor)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    health_check_after = build_shoulder_health_check(
        USER_ID,
        fetch_all_user_records(database),
    )

    print(
        json.dumps(
            {
                "success": True,
                "found_demo_records": demo_records,
                "matching_alerts": [normalize_alert(alert) for alert in matching_alerts],
                "deleted_alerts": deleted_alerts,
                "deleted_records": deleted_records,
                "exercise_records_before": exercise_records_before,
                "exercise_records_after": exercise_records_after,
                "health_check_after": health_check_after,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
