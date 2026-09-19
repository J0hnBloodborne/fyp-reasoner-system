"""Run the local proof of concept."""

import argparse
import logging

from traffic_poc.config import Settings
from traffic_poc.inference import TorchVLM
from traffic_poc.pipeline import Pipeline
from traffic_poc.server import LocalServer
from traffic_poc.storage import Repository


def main() -> None:
    parser = argparse.ArgumentParser(description="Local traffic evidence review")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--warmup", action="store_true", help="Load model at startup")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    settings = Settings.from_env()
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


if __name__ == "__main__":
    main()
