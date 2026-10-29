import copy
import sys
import types
import unittest
from unittest.mock import patch


sys.modules.setdefault("cv2", types.ModuleType("cv2"))
sys.modules.setdefault("numpy", types.ModuleType("numpy"))

exercise_feedback = types.ModuleType("pose.exercise_feedback")
exercise_feedback.analyze_exercise_frame = lambda *args, **kwargs: {}
exercise_feedback.reset_exercise = lambda *args, **kwargs: None
sys.modules.setdefault("pose.exercise_feedback", exercise_feedback)

rom_checker = types.ModuleType("pose.rom_checker")
rom_checker.ROM_EXERCISE_KEY = "rom_shoulder"
rom_checker.analyze_rom_frame = lambda *args, **kwargs: {}
rom_checker.reset_rom_check = lambda *args, **kwargs: None
sys.modules.setdefault("pose.rom_checker", rom_checker)

import app as app_module
from data_store import HealthAlertNotFound
from health_alerts import (
    build_health_alert_candidate,
    decode_source_exercise_record_ids,
)
from health_check import build_shoulder_health_check


FORBIDDEN_ALERT_TERMS = (
    "오십견",
    "관절염",
    "뇌졸중",
    "낙상 고위험",
    "질병 확정",
    "장애 판정",
    "진단됨",
)


def health_check_fixture(user_id, overall_status, *, rom, exercise):
    labels = {
        "normal": "이상 징후 없음",
        "caution": "주의 관찰",
        "check_required": "운동 기능 저하 징후 - 점검 권장",
        "insufficient_data": "데이터 부족",
    }
    return {
        "user_id": user_id,
        "overall_status": overall_status,
        "overall_label": labels[overall_status],
        "rom": rom,
        "exercise": exercise,
        "message": labels[overall_status],
    }


def rom_result(record_id, status, angle):
    return {
        "available": True,
        "record_id": record_id,
        "angle": angle,
        "normal_max": 180,
        "percentage": round(angle / 180 * 100, 1),
        "reduction_percentage": round((180 - angle) / 180 * 100, 1),
        "status": status,
        "label": "정상" if status == "normal" else "주의",
        "started_at": "2026-09-09T00:00:00Z",
    }


def exercise_result(record_ids, status, accuracy_avg):
    return {
        "available": True,
        "recent_count": len(record_ids),
        "record_ids": record_ids,
        "accuracy_avg": accuracy_avg,
        "status": status,
        "label": "양호" if status == "good" else "주의",
    }


class FakeAlertStore:
    def __init__(self, health_checks):
        self.health_checks = copy.deepcopy(health_checks)
        self.alert_rows = []
        self.next_alert_id = 1
        self.user_names = {
            "user-1": "김영희",
            "user-caution": "테스트 주의",
            "user-warning": "테스트 경고",
            "user-other": "다른 보호자 사용자",
        }
        self.guardian_links = {
            "guardian-demo-001": {"user-caution", "user-warning", "user-1"},
            "guardian-other": {"user-other"},
        }

    def get_user_health_check(self, user_id):
        return copy.deepcopy(self.health_checks[user_id])

    def create_health_alert_if_needed(self, user_id, health_check=None):
        health_check = health_check or self.get_user_health_check(user_id)
        candidate = build_health_alert_candidate(user_id, health_check)
        if not candidate:
            return {
                "created": False,
                "reason": health_check["overall_status"],
                "alert": None,
            }

        duplicate = next(
            (
                row
                for row in self.alert_rows
                if row["user_id"] == user_id
                and row["overall_status"] == candidate["overall_status"]
                and row.get("source_rom_record_id")
                == candidate.get("source_rom_record_id")
                and row.get("source_exercise_record_ids")
                == candidate.get("source_exercise_record_ids")
            ),
            None,
        )
        if duplicate:
            return {
                "created": False,
                "reason": "duplicate",
                "alert": self._public_alert(duplicate),
            }

        row = {
            **candidate,
            "alert_id": self.next_alert_id,
            "is_read": False,
            "created_at": f"2026-09-09T00:00:0{self.next_alert_id}Z",
        }
        self.next_alert_id += 1
        self.alert_rows.append(row)
        return {"created": True, "alert": self._public_alert(row)}

    def list_guardian_alerts(self, guardian_id):
        linked_user_ids = self.guardian_links.get(guardian_id, set())
        alerts = [
            row
            for row in self.alert_rows
            if row["user_id"] in linked_user_ids
        ]
        alerts.sort(key=lambda row: (row["created_at"], row["alert_id"]), reverse=True)
        return [self._public_alert(row) for row in alerts]

    def mark_guardian_alert_read(self, guardian_id, alert_id):
        linked_user_ids = self.guardian_links.get(guardian_id, set())
        alert = next(
            (
                row
                for row in self.alert_rows
                if row["alert_id"] == int(alert_id)
                and row["user_id"] in linked_user_ids
            ),
            None,
        )
        if not alert:
            raise HealthAlertNotFound("health alert not found")

        alert["is_read"] = True
        return self._public_alert(alert)

    def _public_alert(self, row):
        return {
            "alert_id": row["alert_id"],
            "user_id": row["user_id"],
            "user_name": self.user_names.get(row["user_id"]),
            "alert_type": row["alert_type"],
            "severity": row["severity"],
            "title": row["title"],
            "message": row["message"],
            "overall_status": row["overall_status"],
            "source_rom_record_id": row.get("source_rom_record_id"),
            "source_exercise_record_ids": decode_source_exercise_record_ids(
                row.get("source_exercise_record_ids")
            ),
            "is_read": bool(row["is_read"]),
            "created_at": row["created_at"],
        }


class HealthAlertApiTest(unittest.TestCase):
    def setUp(self):
        self.health_checks = {
            "user-1": health_check_fixture(
                "user-1",
                "normal",
                rom=rom_result(4, "normal", 159),
                exercise=exercise_result([11, 10, 9], "good", 87.9),
            ),
            "user-caution": health_check_fixture(
                "user-caution",
                "caution",
                rom=rom_result(20, "caution", 128),
                exercise=exercise_result([30, 29, 28], "good", 87.9),
            ),
            "user-warning": health_check_fixture(
                "user-warning",
                "check_required",
                rom=rom_result(21, "normal", 159),
                exercise=exercise_result([40, 39, 38], "reduced", 58.0),
            ),
            "user-other": health_check_fixture(
                "user-other",
                "caution",
                rom=rom_result(22, "caution", 125),
                exercise=exercise_result([50, 49, 48], "good", 86.0),
            ),
        }
        self.store = FakeAlertStore(self.health_checks)
        self.patch = patch.object(app_module, "data_store", self.store)
        self.patch.start()
        self.client = app_module.app.test_client()

    def tearDown(self):
        self.patch.stop()

    def test_health_endpoint_still_works(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"status": "ok"})

    def test_normal_user_does_not_create_alert(self):
        response = self.client.post("/api/users/user-1/health-check/alerts")
        body = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(body["success"])
        self.assertFalse(body["created"])
        self.assertEqual(body["reason"], "normal")
        self.assertIsNone(body["alert"])
        self.assertEqual(body["health_check"]["overall_status"], "normal")

    def test_caution_alert_duplicate_and_source_change(self):
        first = self.client.post("/api/users/user-caution/health-check/alerts")
        first_body = first.get_json()

        self.assertEqual(first.status_code, 201)
        self.assertTrue(first_body["created"])
        self.assertEqual(first_body["alert"]["severity"], "caution")
        self.assertEqual(first_body["alert"]["source_rom_record_id"], 20)
        self.assertEqual(
            first_body["alert"]["source_exercise_record_ids"], [30, 29, 28]
        )
        self.assertNotForbidden(first_body["alert"]["message"])

        duplicate = self.client.post("/api/users/user-caution/health-check/alerts")
        duplicate_body = duplicate.get_json()
        self.assertEqual(duplicate.status_code, 200)
        self.assertFalse(duplicate_body["created"])
        self.assertEqual(duplicate_body["reason"], "duplicate")

        self.store.health_checks["user-caution"]["rom"]["record_id"] = 23
        self.store.health_checks["user-caution"]["rom"]["angle"] = 126

        changed_source = self.client.post(
            "/api/users/user-caution/health-check/alerts"
        )
        changed_body = changed_source.get_json()
        self.assertEqual(changed_source.status_code, 201)
        self.assertTrue(changed_body["created"])
        self.assertEqual(changed_body["alert"]["source_rom_record_id"], 23)

    def test_warning_alert_guardian_list_and_read_permissions(self):
        self.client.post("/api/users/user-warning/health-check/alerts")
        self.client.post("/api/users/user-other/health-check/alerts")

        listing = self.client.get("/api/guardians/guardian-demo-001/alerts")
        listing_body = listing.get_json()
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(
            {alert["user_id"] for alert in listing_body["alerts"]},
            {"user-warning"},
        )

        alert = listing_body["alerts"][0]
        self.assertEqual(alert["severity"], "warning")
        self.assertEqual(alert["overall_status"], "check_required")
        self.assertFalse(alert["is_read"])
        self.assertNotForbidden(alert["message"])

        read_response = self.client.patch(
            f"/api/guardians/guardian-demo-001/alerts/{alert['alert_id']}/read"
        )
        read_body = read_response.get_json()
        self.assertEqual(read_response.status_code, 200)
        self.assertTrue(read_body["alert"]["is_read"])

        blocked_response = self.client.patch(
            f"/api/guardians/guardian-other/alerts/{alert['alert_id']}/read"
        )
        self.assertEqual(blocked_response.status_code, 404)

    def assertNotForbidden(self, text):
        for term in FORBIDDEN_ALERT_TERMS:
            self.assertNotIn(term, text)


class FakeExerciseAlertStore:
    def __init__(self):
        self.records = []
        self.alert_rows = []
        self.next_record_id = 1
        self.next_alert_id = 1
        self.alert_attempts = []
        self.health_check_calls = []
        self.raise_on_alert = False

    def create_exercise_record(self, record):
        saved_record = {
            "record_id": self.next_record_id,
            "user_id": record["user_id"],
            "exercise_key": record["exercise_key"],
            "accuracy_avg": record.get("accuracy_avg"),
            "feedback_summary": record.get("feedback_summary", ""),
            "started_at": record.get("started_at"),
            "ended_at": record.get("ended_at"),
        }
        self.next_record_id += 1
        self.records.append(saved_record)
        return copy.deepcopy(saved_record)

    def list_exercise_records(self, user_id):
        records = [
            record for record in self.records if record.get("user_id") == user_id
        ]
        return copy.deepcopy(list(reversed(records)))

    def get_user_health_check(self, user_id):
        self.health_check_calls.append(user_id)
        return build_shoulder_health_check(user_id, self.list_exercise_records(user_id))

    def create_health_alert_if_needed(self, user_id, health_check=None):
        self.alert_attempts.append(user_id)
        if self.raise_on_alert:
            raise RuntimeError("alert follow-up failed")

        health_check = health_check or self.get_user_health_check(user_id)
        candidate = build_health_alert_candidate(user_id, health_check)
        if not candidate:
            return {
                "created": False,
                "reason": health_check.get("overall_status") or "not_needed",
                "alert": None,
            }

        duplicate = next(
            (
                row
                for row in self.alert_rows
                if row["user_id"] == user_id
                and row["overall_status"] == candidate["overall_status"]
                and row.get("source_rom_record_id")
                == candidate.get("source_rom_record_id")
                and row.get("source_exercise_record_ids")
                == candidate.get("source_exercise_record_ids")
            ),
            None,
        )
        if duplicate:
            return {
                "created": False,
                "reason": "duplicate",
                "alert": self._public_alert(duplicate),
            }

        row = {
            **candidate,
            "alert_id": self.next_alert_id,
            "is_read": False,
            "created_at": f"2026-09-09T00:00:0{self.next_alert_id}Z",
        }
        self.next_alert_id += 1
        self.alert_rows.append(row)
        return {"created": True, "alert": self._public_alert(row)}

    def _public_alert(self, row):
        return {
            "alert_id": row["alert_id"],
            "user_id": row["user_id"],
            "user_name": None,
            "alert_type": row["alert_type"],
            "severity": row["severity"],
            "title": row["title"],
            "message": row["message"],
            "overall_status": row["overall_status"],
            "source_rom_record_id": row.get("source_rom_record_id"),
            "source_exercise_record_ids": decode_source_exercise_record_ids(
                row.get("source_exercise_record_ids")
            ),
            "is_read": bool(row["is_read"]),
            "created_at": row["created_at"],
        }


class ExerciseRecordAutoAlertTest(unittest.TestCase):
    def setUp(self):
        self.store = FakeExerciseAlertStore()
        self.patch = patch.object(app_module, "data_store", self.store)
        self.patch.start()
        self.client = app_module.app.test_client()

    def tearDown(self):
        self.patch.stop()

    def post_record(
        self,
        user_id,
        exercise_key,
        *,
        accuracy_avg=None,
        feedback_summary="",
    ):
        return self.client.post(
            "/api/exercise-records",
            json={
                "user_id": user_id,
                "exercise_key": exercise_key,
                "accuracy_avg": accuracy_avg,
                "feedback_summary": feedback_summary,
                "started_at": "2026-09-09T00:00:00Z",
                "ended_at": "2026-09-09T00:01:00Z",
            },
        )

    def test_shoulder_save_runs_health_check_but_normal_creates_no_alert(self):
        response = self.post_record(
            "auto-normal",
            "shoulder",
            accuracy_avg=90.0,
            feedback_summary="정상 운동 기록",
        )
        body = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(body.keys()), {"success", "record"})
        self.assertTrue(body["success"])
        self.assertEqual(self.store.alert_attempts, ["auto-normal"])
        self.assertEqual(self.store.health_check_calls, ["auto-normal"])
        self.assertEqual(self.store.alert_rows, [])

    def test_shoulder_save_creates_caution_alert(self):
        response = self.post_record(
            "auto-shoulder-caution",
            "shoulder",
            accuracy_avg=65.0,
            feedback_summary="주의 운동 기록",
        )
        body = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.store.health_check_calls, ["auto-shoulder-caution"])
        self.assertEqual(len(self.store.alert_rows), 1)
        self.assertEqual(self.store.alert_rows[0]["overall_status"], "caution")
        self.assertEqual(self.store.alert_rows[0]["severity"], "caution")
        self.assertEqual(
            decode_source_exercise_record_ids(
                self.store.alert_rows[0]["source_exercise_record_ids"]
            ),
            [body["record"]["record_id"]],
        )

    def test_rom_shoulder_save_runs_health_check_and_creates_alert(self):
        response = self.post_record(
            "auto-rom-caution",
            "rom_shoulder",
            feedback_summary="최대 가동 범위 128도, caution로 측정되었습니다.",
        )
        body = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.store.health_check_calls, ["auto-rom-caution"])
        self.assertEqual(len(self.store.alert_rows), 1)
        self.assertEqual(self.store.alert_rows[0]["overall_status"], "caution")
        self.assertEqual(
            self.store.alert_rows[0]["source_rom_record_id"],
            body["record"]["record_id"],
        )

    def test_insufficient_data_creates_no_alert_after_supported_record_save(self):
        response = self.post_record(
            "auto-insufficient",
            "rom_shoulder",
            feedback_summary="가동 범위 측정값을 찾을 수 없습니다.",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.store.alert_attempts, ["auto-insufficient"])
        self.assertEqual(self.store.health_check_calls, ["auto-insufficient"])
        self.assertEqual(self.store.alert_rows, [])

    def test_check_required_creates_warning_alert_and_same_source_dedupes(self):
        response = self.post_record(
            "auto-warning",
            "shoulder",
            accuracy_avg=55.0,
            feedback_summary="점검 필요 운동 기록",
        )
        body = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(self.store.alert_rows), 1)
        self.assertEqual(self.store.alert_rows[0]["overall_status"], "check_required")
        self.assertEqual(self.store.alert_rows[0]["severity"], "warning")
        self.assertEqual(
            decode_source_exercise_record_ids(
                self.store.alert_rows[0]["source_exercise_record_ids"]
            ),
            [body["record"]["record_id"]],
        )

        duplicate = self.client.post("/api/users/auto-warning/health-check/alerts")
        duplicate_body = duplicate.get_json()
        self.assertEqual(duplicate.status_code, 200)
        self.assertFalse(duplicate_body["created"])
        self.assertEqual(duplicate_body["reason"], "duplicate")
        self.assertEqual(len(self.store.alert_rows), 1)

    def test_alert_follow_up_error_does_not_break_exercise_save(self):
        self.store.raise_on_alert = True

        with self.assertLogs(app_module.app.logger.name, level="ERROR") as logs:
            response = self.post_record(
                "auto-alert-error",
                "shoulder",
                accuracy_avg=55.0,
                feedback_summary="점검 필요 운동 기록",
            )
        body = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(body["success"])
        self.assertEqual(body["record"]["user_id"], "auto-alert-error")
        self.assertEqual(len(self.store.records), 1)
        self.assertEqual(self.store.alert_attempts, ["auto-alert-error"])
        self.assertEqual(self.store.alert_rows, [])
        self.assertIn("post-save health alert processing failed", logs.output[0])

    def test_unsupported_exercise_key_skips_auto_alert_processing(self):
        response = self.post_record(
            "auto-knee",
            "knee",
            accuracy_avg=55.0,
            feedback_summary="무릎 기록",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.store.alert_attempts, [])
        self.assertEqual(self.store.health_check_calls, [])


if __name__ == "__main__":
    unittest.main()
