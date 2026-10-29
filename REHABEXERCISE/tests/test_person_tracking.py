"""Deterministic safety tests, without camera, downloaded weights or database."""
import importlib
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch
if "numpy" in sys.modules and not hasattr(sys.modules["numpy"], "zeros"):
    # Existing API tests install an empty NumPy stub; these tests need real arrays.
    del sys.modules["numpy"]
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pose.person_tracking import TargetLock, overlap, crop_box


class TargetTests(unittest.TestCase):
    def acquire(self, lock):
        result = None
        for i in range(5):
            result = lock.update([(7, (180, 40, 300, 330), .9)], 480, 360, i * .6)
        self.assertEqual(result[0], "TRACKING")

    def test_ambiguous_people_never_selected(self):
        lock = TargetLock()
        for i in range(8):
            state, _, _ = lock.update([(1, (140, 40, 260, 330), .9),
                                      (2, (220, 40, 340, 330), .9)], 480, 360, i * .6)
        self.assertEqual(state, "MULTIPLE_PEOPLE")
        self.assertIsNone(lock.target_id)

    def test_larger_bystander_does_not_replace_target(self):
        lock = TargetLock()
        self.acquire(lock)
        state, _, _ = lock.update([(7, (160, 40, 280, 330), .18),
                                  (9, (310, 0, 480, 360), .9)], 480, 360, 3)
        self.assertEqual(state, "TRACKING")
        self.assertEqual(lock.target_id, 7)

    def test_missing_id_requires_manual_confirmation(self):
        lock = TargetLock()
        self.acquire(lock)
        self.assertEqual(lock.update([(8, (180, 40, 300, 330), .9)], 480, 360, 3)[0], "TARGET_LOST")
        self.assertEqual(lock.update([(7, (180, 40, 300, 330), .9)], 480, 360, 3.6)[0], "TARGET_LOST")
        self.assertEqual(lock.target_id, 7)
        lock.reset()
        self.acquire(lock)

    def test_occlusion_recovers_same_id_after_stability(self):
        lock = TargetLock()
        self.acquire(lock)
        state, _, coverage = lock.update([(7, (180, 40, 300, 330), .9),
                                         (8, (200, 40, 320, 330), .9)], 480, 360, 3)
        self.assertEqual(state, "OCCLUDED")
        self.assertGreater(coverage, .4)
        for i in range(3):
            state, _, _ = lock.update([(7, (180, 40, 300, 330), .9)], 480, 360, 3.6 + i * .6)
        self.assertEqual(state, "TRACKING")
        self.assertEqual(lock.target_id, 7)

    def test_discontinuous_box_and_long_gap_pause(self):
        for box, now in [((0, 0, 90, 150), 3), ((180, 40, 300, 330), 8)]:
            lock = TargetLock()
            self.acquire(lock)
            self.assertEqual(lock.update([(7, box, .9)], 480, 360, now)[0], "TARGET_LOST")

    def test_overlap_and_crop(self):
        iou, coverage = overlap((0, 0, 100, 100), (25, 25, 75, 75))
        self.assertEqual(iou, .25)
        self.assertEqual(coverage, .25)
        self.assertEqual(crop_box((0, 0, 100, 100), 120, 110), (0, 0, 120, 110))


class PipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Only inference dependencies are stubbed; real pipeline and analyzers run.
        cls.modules = patch.dict(sys.modules, {"cv2": types.ModuleType("cv2"),
                                               "mediapipe": types.ModuleType("mediapipe")})
        cls.modules.start()
        cls.pd = importlib.import_module("pose.pose_detector")
        cls.ex = importlib.reload(importlib.import_module("pose.exercise_feedback"))
        cls.rom = importlib.reload(importlib.import_module("pose.rom_checker"))

    @classmethod
    def tearDownClass(cls):
        cls.modules.stop()

    def setUp(self):
        self.pd._previous = None
        self.pd._previous_time = None
        self.pd._good_frames = 0
        self.ex._shoulder_tracker.reset()
        self.rom._rom_tracker.reset()

    def landmarks(self):
        return {name: {"x": .5, "y": .5, "z": .1, "visibility": .99,
                       "pixel": (75, 195), "normalized": (.5, .5, .1),
                       "world": (1., 2., 3.)} for name in self.pd.TRACKED_LANDMARKS}

    def test_crop_coordinate_conversion_preserves_world(self):
        box = (180, 40, 300, 330)
        fake = types.SimpleNamespace(detect_pose=lambda f: {"state": "TRACKING", "landmarks": self.landmarks()})
        with patch.object(self.pd, "_detector", fake), patch.object(self.pd._person_tracker, "detect", return_value=("TRACKING", box, 0, [(7, box, .9)])):
            self.pd._person_tracker.lock.target_id = 7
            self.pd.detect_pose(np.zeros((360, 480, 3), dtype=np.uint8))
            result = self.pd.detect_pose(np.zeros((360, 480, 3), dtype=np.uint8))
        self.assertTrue(result["analysis_valid"])
        p = result["landmarks"]["LEFT_WRIST"]
        self.assertEqual(p["pixel"], (240, 180))
        self.assertEqual(p["world"], (1., 2., 3.))
        self.assertAlmostEqual(p["z"], .0375)

    def test_partial_overlap_requires_higher_visibility(self):
        box = (180, 40, 300, 330)
        landmarks = self.landmarks()
        landmarks["LEFT_WRIST"]["visibility"] = .6
        fake = types.SimpleNamespace(detect_pose=lambda f: {"state": "TRACKING", "landmarks": landmarks})
        with patch.object(self.pd, "_detector", fake), patch.object(self.pd._person_tracker, "detect", return_value=("TRACKING", box, .2, [(7, box, .9)])):
            result = self.pd.detect_pose(np.zeros((360, 480, 3), dtype=np.uint8))
        self.assertEqual(result["state"], "LOW_VISIBILITY")

    def test_joint_outlier_does_not_update_baseline(self):
        box = (180, 40, 300, 330)
        self.pd._previous = {name: (240, 180) for name in self.pd.VISIBILITY_LANDMARKS}
        import time
        self.pd._previous_time = time.monotonic()
        baseline = self.pd._previous.copy()
        landmarks = self.landmarks()
        landmarks["LEFT_WRIST"]["x"] = -3
        fake = types.SimpleNamespace(detect_pose=lambda f: {"state": "TRACKING", "landmarks": landmarks})
        with patch.object(self.pd, "_detector", fake), patch.object(self.pd._person_tracker, "detect", return_value=("TRACKING", box, 0, [(7, box, .9)])):
            result = self.pd.detect_pose(np.zeros((360, 480, 3), dtype=np.uint8))
        self.assertEqual(result["state"], "LOW_CONFIDENCE")
        self.assertEqual(self.pd._previous, baseline)

    def test_all_invalid_states_freeze_measurements(self):
        from pose.analysis_states import INVALID_EXERCISE_ANALYSIS_STATES
        self.rom._rom_tracker.max_angle = 93
        self.ex._shoulder_tracker.current_stage = 1
        self.ex._shoulder_tracker.hold_count = 3
        for state in INVALID_EXERCISE_ANALYSIS_STATES:
            pose = {"state": state, "landmarks": None, "analysis_valid": False}
            with patch.object(self.ex, "detect_pose", return_value=pose), patch.object(self.rom, "detect_pose", return_value=pose):
                self.assertFalse(self.ex.analyze_exercise_frame(None)["analysis_valid"])
                self.assertEqual(self.rom.analyze_rom_frame(None)["max_angle"], 93)
            self.assertEqual(self.ex._shoulder_tracker.current_stage, 1)
            self.assertEqual(self.ex._shoulder_tracker.hold_count, 0)

    def test_model_failure_never_falls_back_to_full_frame(self):
        with patch.object(self.pd._person_tracker, "detect", side_effect=RuntimeError("offline")):
            result = self.pd.detect_pose(np.zeros((360, 480, 3), dtype=np.uint8))
        self.assertEqual(result["state"], "TRACKING_ERROR")
        self.assertIsNone(result["landmarks"])

    def test_pause_does_not_erase_rom_or_completed_stage(self):
        self.rom._rom_tracker.max_angle = 120
        self.rom._rom_tracker.last_update = 0
        metrics = {"current_angle": 90, "left_arm_raise_deg": 90, "right_arm_raise_deg": 80,
                   "left_elbow_deg": 150, "right_elbow_deg": 150}
        with patch.object(self.rom, "calculate_shoulder_rom_metrics", return_value=metrics):
            self.assertEqual(self.rom._rom_tracker.analyze({})["max_angle"], 120)
        self.ex._shoulder_tracker.current_stage = 3
        self.ex._shoulder_tracker.completed = True
        self.ex._shoulder_tracker.last_update = 0
        self.assertEqual(self.ex._shoulder_tracker.analyze({})["state"], "COMPLETE")


class SessionTests(unittest.TestCase):
    def test_stale_frames_stop_and_mode_change_rejected(self):
        with patch.dict(sys.modules, {"cv2": types.ModuleType("cv2")}):
            app = importlib.import_module("app")
        client = app.app.test_client()
        with patch.object(app, "reset_pose_tracking"), patch.object(app, "reset_exercise"), patch.object(app, "reset_rom_check"), patch.object(app, "decode_data_url_frame", return_value=np.zeros((360, 480, 3))), patch.object(app, "analyze_exercise_frame", return_value={"state": "STAGE_1", "analysis_valid": True}) as analyze:
            first = client.post("/reset_exercise", json={"use_session": True}).get_json()["analysis_session"]
            second = client.post("/reset_exercise", json={"use_session": True}).get_json()["analysis_session"]
            self.assertNotEqual(first, second)
            self.assertEqual(client.post("/analyze_frame", json={"analysis_session": first}).status_code, 409)
            self.assertEqual(client.post("/stop_exercise", json={"analysis_session": first}).status_code, 409)
            self.assertEqual(client.post("/analyze_frame", json={"analysis_session": second, "mode": "rom_shoulder"}).status_code, 409)
            self.assertEqual(client.post("/analyze_frame", json={"analysis_session": second}).status_code, 200)
            self.assertEqual(analyze.call_count, 1)
            self.assertEqual(client.post("/stop_exercise", json={"analysis_session": second}).status_code, 200)
            self.assertEqual(client.post("/analyze_frame", json={"analysis_session": second}).status_code, 409)


if __name__ == "__main__":
    unittest.main()
