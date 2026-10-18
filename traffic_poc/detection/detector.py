"""The team's Tier-1 trigger heuristics over tracked detections.

Ported from the Colab notebook's final detection cell (YOLO26x + ByteTrack).
Thresholds match that notebook. Constant notebook scores (tailgating 0.88,
red light 0.95) are exported as null because they are not measurements.
"""

import math

import cv2
import numpy as np

TRACKED_CLASSES = [0, 2, 3, 5, 7, 9]
VEHICLE_CLASSES = {2, 3, 5, 7}
TRAFFIC_LIGHT = 9


def calculate_iou(box1, box2) -> float:
    x_left, y_top = max(box1[0], box2[0]), max(box1[1], box2[1])
    x_right, y_bottom = min(box1[2], box2[2]), min(box1[3], box2[3])
    if x_right < x_left or y_bottom < y_top:
        return 0.0
    inter = (x_right - x_left) * (y_bottom - y_top)
    b1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
    b2 = (box2[2] - box2[0]) * (box2[3] - box2[1])
    return inter / float(b1 + b2 - inter)


def get_center(box) -> tuple[float, float]:
    return ((box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0)


def area(box) -> float:
    return (box[2] - box[0]) * (box[3] - box[1])


def traffic_light_state(frame, box) -> str:
    x1, y1, x2, y2 = map(int, box)
    crop = frame[
        max(0, y1) : min(frame.shape[0], y2), max(0, x1) : min(frame.shape[1], x2)
    ]
    if crop.size == 0:
        return "UNKNOWN"
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    red = cv2.countNonZero(
        cv2.inRange(hsv, np.array([0, 70, 50]), np.array([10, 255, 255]))
        | cv2.inRange(hsv, np.array([170, 70, 50]), np.array([180, 255, 255]))
    )
    green = cv2.countNonZero(
        cv2.inRange(hsv, np.array([40, 70, 50]), np.array([90, 255, 255]))
    )
    if red > green and red > 15:
        return "RED"
    if green > red and green > 15:
        return "GREEN"
    return "UNKNOWN"


class Detector:
    """Stateful notebook heuristics over per-frame tracked detections."""

    def __init__(self, camera_type: str, allowed_direction_y: int = -1):
        self.camera_type = camera_type
        self.allowed_direction_y = allowed_direction_y
        self.stop_line_y = None
        self.prev_gray = None
        self.tracks: dict[int, list[tuple[int, float, float]]] = {}
        self.fired: set[str] = set()
        self.violations: list[dict] = []

    def _log(self, key: str, frame_index: int, kind: str, target, value) -> None:
        if key in self.fired:
            return
        self.fired.add(key)
        self.violations.append(
            {
                "frame": frame_index,
                "type": kind,
                "target_id": target,
                "confidence": None if value is None else round(float(value), 2),
            }
        )

    def observe(self, frame_index: int, frame, detections) -> None:
        """detections: iterable of (xyxy box, class id, track id)."""
        h, w = frame.shape[:2]
        frame_area = h * w
        if self.stop_line_y is None:
            self.stop_line_y = int(h * 0.65)

        if self.camera_type == "DASHCAM":
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            if self.prev_gray is not None:
                shift = np.mean(cv2.absdiff(self.prev_gray, gray))
                if shift > 18.0:
                    self._log(
                        "Ego Impact",
                        frame_index,
                        "Ego Collision (Pixel Shift Spike)",
                        "Camera",
                        shift,
                    )
            self.prev_gray = gray

        vehicles, lights = [], []
        for box, cls, tid in detections:
            if cls in VEHICLE_CLASSES:
                vehicles.append((box, tid))
            elif cls == TRAFFIC_LIGHT:
                lights.append(box)
            x, y = get_center(box)
            self.tracks.setdefault(tid, []).append((frame_index, x, y))

        if self.camera_type == "DASHCAM":
            for box, tid in vehicles:
                ratio = area(box) / frame_area
                if ratio > 0.05:
                    self._log(
                        "Looming",
                        frame_index,
                        "Ego-Vehicle Collision (Looming)",
                        f"ID {tid} -> Camera",
                        ratio,
                    )

        for i in range(len(vehicles)):
            for j in range(i + 1, len(vehicles)):
                (b1, tid1), (b2, tid2) = vehicles[i], vehicles[j]
                if area(b1) / frame_area < 0.015 or area(b2) / frame_area < 0.015:
                    continue
                iou = calculate_iou(b1, b2)
                if iou > 0.85:
                    continue
                (x1, y1), (x2, y2) = get_center(b1), get_center(b2)
                if iou > 0.12 or math.hypot(x2 - x1, y2 - y1) < 55.0:
                    self._log(
                        "Collision",
                        frame_index,
                        "Multi-Vehicle Collision",
                        f"{tid1} & {tid2}",
                        iou,
                    )

        for _, tid in vehicles:
            history = self.tracks[tid]
            if len(history) >= 15:
                dy = history[-1][2] - history[0][2]
                if (self.allowed_direction_y < 0 and dy > 20.0) or (
                    self.allowed_direction_y > 0 and dy < -20.0
                ):
                    self._log(
                        f"Wrong-Way-{tid}",
                        frame_index,
                        "Wrong-Way Driving",
                        f"ID {tid}",
                        abs(dy),
                    )

        for lead_box, lead_id in vehicles:
            for rear_box, rear_id in vehicles:
                if rear_id == lead_id:
                    continue
                x_diff = abs(get_center(lead_box)[0] - get_center(rear_box)[0])
                y_gap = rear_box[1] - lead_box[3]
                if 0 < y_gap < 15 and x_diff < 40:
                    self._log(
                        f"Tailgating-{rear_id}",
                        frame_index,
                        "Unsafe Following",
                        f"{rear_id} -> {lead_id}",
                        None,
                    )

        signal = next(
            (
                state
                for state in (traffic_light_state(frame, box) for box in lights)
                if state in {"RED", "GREEN"}
            ),
            "UNKNOWN",
        )
        if signal == "RED":
            for _, tid in vehicles:
                history = self.tracks[tid]
                if len(history) >= 2 and (
                    history[-2][2] < self.stop_line_y <= history[-1][2]
                ):
                    self._log(
                        f"RedLight-{tid}",
                        frame_index,
                        "Red-Light Running",
                        f"ID {tid}",
                        None,
                    )
