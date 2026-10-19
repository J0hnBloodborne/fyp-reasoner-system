"""Decode a video to frames and run YOLO + ByteTrack through the detector."""

import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

import cv2

from traffic_poc.detection.detector import TRACKED_CLASSES, Detector

Progress = Callable[[int, int], None]


def extract_frames(
    video: Path, directory: Path, progress: Progress | None = None
) -> tuple[list[Path], float | None]:
    """Write every decoded frame as JPEG; bundle evidence uses these files."""
    directory.mkdir(parents=True, exist_ok=False)
    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        raise ValueError(f"Cannot open video: {video}")
    fps = capture.get(cv2.CAP_PROP_FPS) or None
    total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    paths = []
    while True:
        ok, frame = capture.read()
        if not ok:
            break
        path = directory / f"frame_{len(paths):06d}.jpg"
        cv2.imwrite(str(path), frame)
        paths.append(path)
        if progress and len(paths) % 50 == 0:
            progress(len(paths), max(total, len(paths)))
    capture.release()
    if not paths:
        raise ValueError(f"No frames decoded from {video}")
    return paths, fps


def detect(
    frame_paths: list[Path],
    detector: Detector,
    weights: Path,
    progress: Progress | None = None,
) -> list[dict]:
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
        if progress and frame_index % 25 == 0:
            progress(frame_index, len(frame_paths))
    return detector.violations


def make_preview(video: Path, destination: Path) -> bool:
    """Write a 720p H.264 MP4 that any browser can seek; needs ffmpeg on PATH.

    Without ffmpeg the original file is played, which browsers may not decode.
    """
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return False
    command = [
        ffmpeg, "-v", "error", "-y", "-i", str(video),
        "-vf", "scale=-2:'min(720,ih)'", "-c:v", "libx264", "-preset", "veryfast",
        "-crf", "26", "-pix_fmt", "yuv420p", "-an", "-movflags", "+faststart",
        str(destination),
    ]  # fmt: skip
    subprocess.run(command, check=True, capture_output=True, timeout=1800)
    return True
