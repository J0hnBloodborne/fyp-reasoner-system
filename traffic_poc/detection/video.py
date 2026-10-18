"""Decode a video to frames and run YOLO + ByteTrack through the detector."""

from pathlib import Path

import cv2

from traffic_poc.detection.detector import TRACKED_CLASSES, Detector


def extract_frames(video: Path, directory: Path) -> tuple[list[Path], float | None]:
    """Write every decoded frame as JPEG; bundle evidence uses these files."""
    directory.mkdir(parents=True, exist_ok=False)
    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        raise ValueError(f"Cannot open video: {video}")
    fps = capture.get(cv2.CAP_PROP_FPS) or None
    paths = []
    while True:
        ok, frame = capture.read()
        if not ok:
            break
        path = directory / f"frame_{len(paths):06d}.jpg"
        cv2.imwrite(str(path), frame)
        paths.append(path)
    capture.release()
    if not paths:
        raise ValueError(f"No frames decoded from {video}")
    return paths, fps


def detect(frame_paths: list[Path], detector: Detector, weights: Path) -> list[dict]:
    from ultralytics import YOLO

    model = YOLO(str(weights))
    for frame_index, path in enumerate(frame_paths, start=1):
        frame = cv2.imread(str(path))
        result = model.track(
            frame,
            persist=True,
            tracker="bytetrack.yaml",
            classes=TRACKED_CLASSES,
            conf=0.08,
            verbose=False,
        )[0]
        detections = []
        if result.boxes and result.boxes.id is not None:
            detections = zip(
                result.boxes.xyxy.cpu().numpy(),
                result.boxes.cls.cpu().numpy().astype(int),
                result.boxes.id.cpu().numpy().astype(int),
                strict=True,
            )
        detector.observe(frame_index, frame, detections)
    return detector.violations
