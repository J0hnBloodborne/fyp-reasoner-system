"""Run Tier-1 detection on a local video and write an event bundle."""

import argparse
from pathlib import Path

from traffic_poc.config import ROOT, Settings
from traffic_poc.detection.detector import Detector
from traffic_poc.detection.export_bundle import export_bundle
from traffic_poc.detection.video import detect, extract_frames


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Tier-1 detection on a video")
    parser.add_argument("video", type=Path)
    parser.add_argument("--camera-type", choices=["CCTV", "DASHCAM"], default="CCTV")
    parser.add_argument(
        "--allowed-direction",
        type=int,
        choices=[-1, 1],
        default=-1,
        help="-1: normal traffic moves up the screen; 1: down",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    settings = Settings.from_env()
    stem = args.video.stem
    frames, fps = extract_frames(args.video, settings.data_dir / "tier1_frames" / stem)
    print(f"Extracted {len(frames)} frames at {fps} fps")
    violations = detect(
        frames,
        Detector(args.camera_type, args.allowed_direction),
        ROOT / "models" / "yolo26x.pt",
    )
    if not violations:
        print("No Tier-1 thresholds breached; no bundle written")
        return
    for row in violations:
        print(row)
    output = args.output or settings.data_dir / f"{stem}_tier1.zip"
    export_bundle(
        violations, frames, args.video.name, args.camera_type, output, fps=fps
    )
    print(f"Bundle: {output}")


if __name__ == "__main__":
    main()
