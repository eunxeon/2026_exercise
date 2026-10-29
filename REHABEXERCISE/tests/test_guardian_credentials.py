"""Authentication regression checks using isolated mock state, never MSSQL."""
import copy
import secrets
import unittest
from unittest.mock import patch

# Reuse the existing API test's camera stubs.
from test_health_alerts import app_module
import mock_data
from werkzeug.security import generate_password_hash


class GuardianCredentialTests(unittest.TestCase):
    def setUp(self):
        self.saved = copy.deepcopy(mock_data.GUARDIANS)
        self.db_patch = patch.object(app_module.data_store.database, "is_configured", return_value=False)
        self.db_patch.start()
        self.client = app_module.app.test_client()

    def tearDown(self):
        mock_data.GUARDIANS[:] = self.saved
        self.db_patch.stop()

    def test_configured_demo_login_and_linked_users(self):
        password = secrets.token_urlsafe(24)
        mock_data.GUARDIANS[0]["password_hash"] = generate_password_hash(password)
        result = self.client.post("/api/auth/login", json={"login_id": "demo_guardian", "password": password})
        self.assertEqual(result.status_code, 200)
        self.assertNotIn("password_hash", result.get_json())
        users = self.client.get("/api/guardians/guardian-demo-001/users").get_json()["users"]
        self.assertTrue(any(user["id"] == "user-1" for user in users))
        self.assertEqual(self.client.post("/api/auth/login", json={"login_id": "demo_guardian", "password": "incorrect"}).status_code, 401)

    def test_missing_demo_hash_denies_login(self):
        mock_data.GUARDIANS[0]["password_hash"] = ""
        self.assertEqual(self.client.post("/api/auth/login", json={"login_id": "demo_guardian", "password": "anything"}).status_code, 401)

    def test_registration_login_and_duplicate(self):
        payload = {"login_id": "isolated-test-guardian", "password": secrets.token_urlsafe(24), "name": "테스트 보호자"}
        self.assertEqual(self.client.post("/api/auth/register", json=payload).status_code, 201)
        self.assertEqual(self.client.post("/api/auth/login", json=payload).status_code, 200)
        self.assertEqual(self.client.post("/api/auth/register", json=payload).status_code, 409)
