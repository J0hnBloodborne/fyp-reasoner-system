"""Run the real model through the same pipeline used by the browser."""

import argparse
import base64
import json
import sys
from pathlib import Path

from traffic_poc.config import Settings
from traffic_poc.inference import TorchVLM
from traffic_poc.pipeline import Pipeline
from traffic_poc.schemas import Review, Submission
from traffic_poc.storage import Repository


def main() -> None:
    parser = argparse.ArgumentParser(description="Real-GPU single-image smoke check")
    parser.add_argument("image")
    parser.add_argument("--runs", type=int, default=2)
    args = parser.parse_args()
    image_path = Path(args.image)
    settings = Settings.from_env()
    model = TorchVLM(settings)
    pipeline = Pipeline(settings, model, Repository(settings.data_dir))
    failed = False
    try:
        for index in range(args.runs):
            record_id = pipeline.submit(
                Submission(
                    image_base64=base64.b64encode(image_path.read_bytes()).decode(),
                    filename=image_path.name,
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


if __name__ == "__main__":
    main()
