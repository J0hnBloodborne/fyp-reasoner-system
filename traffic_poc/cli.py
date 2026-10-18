"""Command line entry point: python -m traffic_poc <command>."""

import argparse
import base64
import json
import logging
import sys
from pathlib import Path

from traffic_poc.config import ROOT, Settings
from traffic_poc.detection.bundle import import_bundle
from traffic_poc.detection.detector import Detector
from traffic_poc.detection.export_bundle import export_bundle
from traffic_poc.detection.video import detect, extract_frames
from traffic_poc.pipeline import Pipeline, Submission
from traffic_poc.records.reviews import Review
from traffic_poc.records.store import Repository
from traffic_poc.vlm.model import TorchVLM
from traffic_poc.web.server import LocalServer


def serve(args: argparse.Namespace, settings: Settings) -> None:
    """Run the local review app; Ctrl+C drains accepted jobs."""
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    server = LocalServer(args.port)
    pipeline = None
    try:
        model = TorchVLM(settings)
        pipeline = Pipeline(settings, model, Repository(settings.data_dir))
        server.pipeline = pipeline
        if args.warmup:
            model.warmup()
        logging.info("Traffic review: http://127.0.0.1:%s", server.server_port)
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        logging.info("Stopping; draining accepted jobs")
    finally:
        server.server_close()
        if pipeline:
            pipeline.close()


def detect_video(args: argparse.Namespace, settings: Settings) -> None:
    """Run Tier-1 detection on a video and write an event bundle."""
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


def import_events(args: argparse.Namespace, settings: Settings) -> None:
    """Import a Tier-1 bundle without loading the VLM; `serve` verifies it."""
    ids = import_bundle(args.bundle, settings, Repository(settings.data_dir))
    print(json.dumps({"record_ids": ids, "status": "awaiting_review"}, indent=2))


def download_model(args: argparse.Namespace, settings: Settings) -> None:
    """Fetch only inference artifacts; do not load weights into VRAM."""
    from huggingface_hub import snapshot_download

    path = snapshot_download(
        settings.model_id,
        revision=settings.revision,
        cache_dir=str(settings.model_cache),
        max_workers=2,
        allow_patterns=["*.json", "*.safetensors", "*.jinja", "*.txt"],
        local_files_only=settings.offline,
    )
    print(f"Model snapshot ready: {path}")


def smoke(args: argparse.Namespace, settings: Settings) -> None:
    """Run the real model through the same pipeline the browser uses."""
    model = TorchVLM(settings)
    pipeline = Pipeline(settings, model, Repository(settings.data_dir))
    failed = False
    try:
        for index in range(args.runs):
            record_id = pipeline.submit(
                Submission(
                    image_base64=base64.b64encode(args.image.read_bytes()).decode(),
                    filename=args.image.name,
                )
            )
            record = pipeline.wait(record_id, timeout=600)
            print(
                json.dumps(
                    {
                        "run": index + 1,
                        "id": record_id,
                        "status": record["status"],
                        "error": record["error"],
                        "analysis": record["analysis"],
                        "provenance": record["provenance"],
                    },
                    indent=2,
                )
            )
            if record["status"] != "completed":
                failed = True
                continue
            pipeline.repository.review(
                record_id,
                Review(
                    decision="rejected",
                    reviewer="smoke_test",
                    notes="Technical smoke check only; not a human-confirmed traffic finding.",
                ),
            )
    finally:
        pipeline.close()
    if failed:
        sys.exit(1)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m traffic_poc")
    commands = parser.add_subparsers(dest="command", required=True)

    command = commands.add_parser("serve", help="run the local review app")
    command.add_argument("--port", type=int, default=8000)
    command.add_argument("--warmup", action="store_true", help="load model at startup")
    command.set_defaults(run=serve)

    command = commands.add_parser("detect", help="run Tier-1 detection on a video")
    command.add_argument("video", type=Path)
    command.add_argument("--camera-type", choices=["CCTV", "DASHCAM"], default="CCTV")
    command.add_argument(
        "--allowed-direction",
        type=int,
        choices=[-1, 1],
        default=-1,
        help="-1: normal traffic moves up the screen; 1: down",
    )
    command.add_argument("--output", type=Path)
    command.set_defaults(run=detect_video)

    command = commands.add_parser("import", help="import a Tier-1 bundle")
    command.add_argument("bundle", type=Path)
    command.set_defaults(run=import_events)

    command = commands.add_parser("download-model", help="fetch the VLM checkpoint")
    command.set_defaults(run=download_model)

    command = commands.add_parser("smoke", help="real-GPU single-image check")
    command.add_argument("image", type=Path)
    command.add_argument("--runs", type=int, default=2)
    command.set_defaults(run=smoke)

    args = parser.parse_args(argv)
    args.run(args, Settings.from_env())
