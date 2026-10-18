"""Notebook heuristic port tests with synthetic tracks; YOLO is never loaded."""

import numpy as np

from traffic_poc.detection.detector import Detector

FRAME = np.zeros((480, 640, 3), dtype=np.uint8)
CAR = 2


def car(x, y, size=80):
    return np.array([x, y, x + size, y + size], dtype=float)


def test_wrong_way_needs_fifteen_frames_against_allowed_direction():
    detector = Detector("CCTV", allowed_direction_y=-1)
    for frame_index in range(1, 15):
        detector.observe(
            frame_index, FRAME, [(car(100, 100 + 2 * frame_index), CAR, 7)]
        )
    assert detector.violations == []
    detector.observe(15, FRAME, [(car(100, 130), CAR, 7)])
    detector.observe(16, FRAME, [(car(100, 132), CAR, 7)])
    assert detector.violations == [
        {
            "frame": 15,
            "type": "Wrong-Way Driving",
            "target_id": "ID 7",
            "confidence": 28.0,
        }
    ]


def test_collision_fires_once_and_ignores_double_boxes():
    detector = Detector("CCTV")
    detector.observe(1, FRAME, [(car(100, 100), CAR, 1), (car(101, 101), CAR, 2)])
    assert detector.violations == []
    detector.observe(2, FRAME, [(car(100, 100), CAR, 1), (car(140, 100), CAR, 3)])
    detector.observe(3, FRAME, [(car(100, 100), CAR, 1), (car(140, 100), CAR, 3)])
    assert [row["type"] for row in detector.violations] == ["Multi-Vehicle Collision"]
    assert detector.violations[0]["target_id"] == "1 & 3"


def test_constant_notebook_scores_export_as_null():
    detector = Detector("CCTV")
    lead, rear = car(300, 100), car(305, 190)
    detector.observe(1, FRAME, [(lead, CAR, 1), (rear, CAR, 2)])
    assert detector.violations == [
        {
            "frame": 1,
            "type": "Unsafe Following",
            "target_id": "2 -> 1",
            "confidence": None,
        }
    ]


def test_pixel_shift_only_in_dashcam_mode():
    bright = np.full_like(FRAME, 255)
    for camera_type, expected in (
        ("CCTV", []),
        ("DASHCAM", ["Ego Collision (Pixel Shift Spike)"]),
    ):
        detector = Detector(camera_type)
        detector.observe(1, FRAME, [])
        detector.observe(2, bright, [])
        assert [row["type"] for row in detector.violations] == expected
