import json
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from data_store import SmartMirrorDataStore  # noqa: E402
from db import MSSQLDatabase  # noqa: E402
from health_check import build_shoulder_health_check  # noqa: E402


GUARDIAN_ID = "guardian-demo-001"
USER_ID = "user-1"
EXPECTED_USER_NAME = "김영희"
DEMO_MARKER = "[presentation-health-demo]"

TARGET_ROM_ANGLE = 128
TARGET_ROM_STATUS = "caution"
TARGET_EXERCISE_AVG = 72.0
TARGET_EXERCISE_STATUS = "caution"
TARGET_OVERALL_STATUS = "check_required"

ROM_RECORD = {
    "exercise_key": "rom_shoulder",
    "accuracy_avg": None,
    "feedback_summary": (
        f"최대 가동 범위 {TARGET_ROM_ANGLE}도, "
        f"주의가 필요한 범위로 측정되었습니다. {DEMO_MARKER}"
    ),
    "duration_seconds": 32,
    "start_offset": timedelta(minutes=1),
}

SHOULDER_RECORDS = [
    {
        "accuracy_avg": 70.0,
        "feedback_summary": (
            f"일부 동작에서 기준 자세와 차이가 확인되었습니다. {DEMO_MARKER}"
        ),
        "duration_seconds": 44,
        "start_offset": timedelta(minutes=4),
    },
    {
        "accuracy_avg": 72.0,
        "feedback_summary": (
            f"운동 자세가 대체로 수행되었으나 일부 자세 교정이 필요합니다. {DEMO_MARKER}"
        ),
        "duration_seconds": 50,
        "start_offset": timedelta(minutes=3),
    },
    {
        "accuracy_avg": 74.0,
        "feedback_summary": (
            f"운동 동작을 수행했으며 일부 구간에서 자세 보완이 필요합니다. {DEMO_MARKER}"
        ),
        "duration_seconds": 55,
        "start_offset": timedelta(minutes=2),
    },
]


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


def fetch_exercise_keys(cursor):
    cursor.execute(
        """
        SELECT exercise_key
        FROM Exercises
        WHERE exercise_key IN (?, ?)
        """,
        "shoulder",
        "rom_shoulder",
    )
    return {row[0] for row in cursor.fetchall()}


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


def validate_existing_demo_records(records):
    rom_records = [
        record for record in records if record["exercise_key"] == "rom_shoulder"
    ]
    shoulder_records = [
        record for record in records if record["exercise_key"] == "shoulder"
    ]
    if len(rom_records) != 1 or len(shoulder_records) != 3:
        raise SystemExit(
            "Existing presentation demo records are incomplete or duplicated. "
            "Run cleanup_presentation_health_demo.py before creating them again."
        )

    rom = rom_records[0]
    if rom["accuracy_avg"] is not None:
        raise SystemExit("Existing presentation ROM record has unexpected accuracy_avg.")
    if f"최대 가동 범위 {TARGET_ROM_ANGLE}도" not in rom["feedback_summary"]:
        raise SystemExit("Existing presentation ROM record does not contain 128 degrees.")

    accuracies = sorted(round(float(record["accuracy_avg"]), 1) for record in shoulder_records)
    if accuracies != [70.0, 72.0, 74.0]:
        raise SystemExit(
            f"Existing presentation shoulder accuracies are {accuracies}, expected [70.0, 72.0, 74.0]."
        )


def insert_exercise_record(cursor, *, exercise_key, accuracy_avg, feedback_summary, started_at, ended_at):
    cursor.execute(
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
        USER_ID,
        exercise_key,
        accuracy_avg,
        feedback_summary,
        started_at,
        ended_at,
    )
    return normalize_record(cursor_row_to_dict(cursor, cursor.fetchone()))


def insert_demo_records(cursor):
    now_utc = datetime.now(timezone.utc).replace(microsecond=0, tzinfo=None)
    inserted = []

    for spec in SHOULDER_RECORDS:
        started_at = now_utc - spec["start_offset"]
        ended_at = started_at + timedelta(seconds=spec["duration_seconds"])
        inserted.append(
            insert_exercise_record(
                cursor,
                exercise_key="shoulder",
                accuracy_avg=spec["accuracy_avg"],
                feedback_summary=spec["feedback_summary"],
                started_at=started_at,
                ended_at=ended_at,
            )
        )

    rom_started_at = now_utc - ROM_RECORD["start_offset"]
    rom_ended_at = rom_started_at + timedelta(seconds=ROM_RECORD["duration_seconds"])
    inserted.append(
        insert_exercise_record(
            cursor,
            exercise_key=ROM_RECORD["exercise_key"],
            accuracy_avg=ROM_RECORD["accuracy_avg"],
            feedback_summary=ROM_RECORD["feedback_summary"],
            started_at=rom_started_at,
            ended_at=rom_ended_at,
        )
    )

    return inserted


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


def assert_health_check_matches(health_check, demo_records):
    rom_records = [
        record for record in demo_records if record["exercise_key"] == "rom_shoulder"
    ]
    shoulder_record_ids = {
        record["record_id"]
        for record in demo_records
        if record["exercise_key"] == "shoulder"
    }

    rom = health_check.get("rom") or {}
    exercise = health_check.get("exercise") or {}

    failures = []
    if health_check.get("overall_status") != TARGET_OVERALL_STATUS:
        failures.append(f"overall_status={health_check.get('overall_status')!r}")
    if rom.get("angle") != TARGET_ROM_ANGLE:
        failures.append(f"rom.angle={rom.get('angle')!r}")
    if rom.get("status") != TARGET_ROM_STATUS:
        failures.append(f"rom.status={rom.get('status')!r}")
    if rom_records and rom.get("record_id") != rom_records[0]["record_id"]:
        failures.append(f"rom.record_id={rom.get('record_id')!r}")
    if exercise.get("recent_count") != 3:
        failures.append(f"exercise.recent_count={exercise.get('recent_count')!r}")
    if exercise.get("accuracy_avg") != TARGET_EXERCISE_AVG:
        failures.append(f"exercise.accuracy_avg={exercise.get('accuracy_avg')!r}")
    if exercise.get("status") != TARGET_EXERCISE_STATUS:
        failures.append(f"exercise.status={exercise.get('status')!r}")
    if set(exercise.get("record_ids") or []) != shoulder_record_ids:
        failures.append(f"exercise.record_ids={exercise.get('record_ids')!r}")

    if failures:
        raise SystemExit(
            "Final health-check did not match the presentation target: "
            + ", ".join(failures)
        )


def normalize_alert(alert):
    if not alert:
        return None
    return dict(alert)


def main():
    configure_stdout()

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
                f"{USER_ID} name is {guardian_link['user_name']!r}, "
                f"expected {EXPECTED_USER_NAME!r}; aborting without changes."
            )

        exercise_keys = fetch_exercise_keys(cursor)
        missing_exercises = {"shoulder", "rom_shoulder"} - exercise_keys
        if missing_exercises:
            raise SystemExit(
                f"Required Exercises rows are missing: {sorted(missing_exercises)}"
            )

        exercise_records_before = count_user_records(cursor)
        existing_demo_records = fetch_demo_records(cursor, lock=True)
        if existing_demo_records:
            validate_existing_demo_records(existing_demo_records)
            inserted_records = []
            demo_records = existing_demo_records
            action = "kept_existing_demo_records"
        else:
            inserted_records = insert_demo_records(cursor)
            demo_records = fetch_demo_records(cursor, lock=True)
            validate_existing_demo_records(demo_records)
            action = "created_demo_records"

        exercise_records_after_insert = count_user_records(cursor)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    all_records = fetch_all_user_records(database)
    health_check = build_shoulder_health_check(USER_ID, all_records)
    assert_health_check_matches(health_check, demo_records)

    store = SmartMirrorDataStore(database)
    store.fallback_enabled = False
    alert_result = store.create_health_alert_if_needed(USER_ID, health_check)
    guardian_alerts = store.list_guardian_alerts(GUARDIAN_ID)
    alert = normalize_alert(alert_result.get("alert"))

    if not alert:
        raise SystemExit("Expected a HealthAlert candidate, but no alert was returned.")
    if alert.get("severity") != "warning":
        raise SystemExit(f"Expected warning alert severity, got {alert.get('severity')!r}.")
    if alert.get("overall_status") != TARGET_OVERALL_STATUS:
        raise SystemExit(
            f"Expected alert overall_status {TARGET_OVERALL_STATUS!r}, "
            f"got {alert.get('overall_status')!r}."
        )

    output = {
        "success": True,
        "action": action,
        "guardian_link": guardian_link,
        "exercise_records_before": exercise_records_before,
        "exercise_records_after_insert": exercise_records_after_insert,
        "inserted_records": inserted_records,
        "demo_records": demo_records,
        "health_check": health_check,
        "alert_result": {
            "created": bool(alert_result.get("created")),
            "reason": alert_result.get("reason"),
            "alert": alert,
        },
        "guardian_alerts_count": len(guardian_alerts),
        "guardian_alert": next(
            (
                item
                for item in guardian_alerts
                if int(item["alert_id"]) == int(alert["alert_id"])
            ),
            None,
        ),
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
