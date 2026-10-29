"""PC-only detector and conservative target lock. No automatic ID replacement."""
import math
import os
import time
from pathlib import Path


def area(box):
    return max(0, box[2] - box[0]) * max(0, box[3] - box[1])


def overlap(a, b):
    intersection = area((max(a[0], b[0]), max(a[1], b[1]),
                         min(a[2], b[2]), min(a[3], b[3])))
    return (intersection / max(1, area(a) + area(b) - intersection),
            intersection / max(1, area(a)))


def crop_box(box, width, height):
    # Arms can extend beyond the person detector box.
    dx, dy = (box[2] - box[0]) * .25, (box[3] - box[1]) * .15
    return (max(0, int(box[0] - dx)), max(0, int(box[1] - dy)),
            min(width, math.ceil(box[2] + dx)), min(height, math.ceil(box[3] + dy)))


class TargetLock:
    def __init__(self):
        self.reset()

    def reset(self):
        self.target_id = None
        self.box = None
        self.candidate_id = None
        self.stable = 0
        self.recovery = 0
        self.requires_confirmation = False
        self.last_time = None

    def update(self, tracks, width, height, now=None):
        now = time.monotonic() if now is None else now
        gap = now - self.last_time if self.last_time is not None else 0
        self.last_time = now
        roi = (.25 * width, .1 * height, .75 * width, .95 * height)
        if self.requires_confirmation:
            return "TARGET_LOST", None, 0
        if self.target_id is None:
            candidates = []
            for track_id, box, confidence in tracks:
                cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
                fraction = area(box) / (width * height)
                inside = overlap(box, roi)[1]
                if confidence < .35 or not (.04 <= fraction <= .8) or inside < .55:
                    continue
                if not (roi[0] <= cx <= roi[2] and roi[1] <= cy <= roi[3]):
                    continue
                center = abs(cx / width - .5) * 2
                size_score = max(0, 1 - abs(fraction - .28) / .4)
                candidates.append((.5 * inside + .4 * (1 - center) + .1 * size_score, track_id, box))
            candidates.sort(reverse=True)
            if not candidates or (len(candidates) > 1 and candidates[0][0] - candidates[1][0] < .12):
                self.candidate_id, self.stable = None, 0
                return ("MULTIPLE_PEOPLE" if candidates else "WAITING_TARGET"), None, 0
            _, candidate, box = candidates[0]
            self.stable = self.stable + 1 if candidate == self.candidate_id and gap < 2 else 1
            self.candidate_id = candidate
            if self.stable < 3:
                return "WAITING_TARGET", None, 0
            self.target_id, self.box = candidate, box
        target = next((box for tid, box, _ in tracks if tid == self.target_id), None)
        if target is None or gap > 2:
            self.requires_confirmation = True
            return "TARGET_LOST", None, 0
        previous = self.box
        scale = max(1, math.sqrt(area(previous)))
        movement = math.hypot((target[0] + target[2] - previous[0] - previous[2]) / 2,
                              (target[1] + target[3] - previous[1] - previous[3]) / 2) / scale
        ratio = area(target) / max(1, area(previous))
        if movement > .65 or not .45 <= ratio <= 2.2:
            self.requires_confirmation = True
            return "TARGET_LOST", None, 0
        self.box = target
        coverage = max((overlap(target, box)[1] for tid, box, _ in tracks
                        if tid != self.target_id), default=0)
        iou = max((overlap(target, box)[0] for tid, box, _ in tracks
                   if tid != self.target_id), default=0)
        if coverage >= .4 or iou >= .3:
            self.recovery = 0
            return "OCCLUDED", target, coverage
        self.recovery += 1
        if self.recovery < 3:
            return "STABILIZING", target, coverage
        return "TRACKING", target, coverage


class PersonTracker:
    def __init__(self):
        self.model = None
        self.tracker = None
        self.lock = TargetLock()

    def reset(self):
        self.lock.reset()
        if self.tracker is not None:
            self.tracker.reset()

    def detect(self, frame):
        if self.model is None:
            from ultralytics import YOLO
            from ultralytics.trackers.byte_tracker import BYTETracker
            from types import SimpleNamespace
            import yaml
            with Path(__file__).with_name("bytetrack.yaml").open(encoding="utf-8") as config:
                self.tracker = BYTETracker(SimpleNamespace(**yaml.safe_load(config)))
            self.model = YOLO(os.getenv("PERSON_MODEL", "yolo11n.pt"))
        # One detector pass; preserve ALL detections before ByteTrack filters them.
        result = self.model.predict(frame, classes=[0], conf=.1,
                                    imgsz=int(os.getenv("PERSON_IMGSZ", "480")),
                                    verbose=False)[0]
        boxes = result.boxes
        tracked = self.tracker.update(boxes.cpu().numpy(), frame)
        tracks = [(int(row[4]), tuple(map(float, row[:4])), float(row[5])) for row in tracked]
        h, w = frame.shape[:2]
        state, box, coverage = self.lock.update(tracks, w, h)
        # Include untracked low-confidence detections in the occlusion gate.
        if box is not None and boxes is not None:
            matched = next((int(row[-1]) for row in tracked if int(row[4]) == self.lock.target_id), -1)
            for index, other in enumerate(boxes.xyxy.cpu().tolist()):
                if index == matched:
                    continue
                coverage = max(coverage, overlap(box, other)[1])
            if coverage >= .4:
                state = "OCCLUDED"
                self.lock.recovery = 0
        return state, box, coverage, tracks
