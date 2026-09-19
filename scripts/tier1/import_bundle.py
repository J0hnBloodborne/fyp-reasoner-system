"""Import a Tier-1 ZIP into the local record store without loading the VLM."""

import argparse
import json
from pathlib import Path

from traffic_poc.config import Settings
from traffic_poc.records.storage import Repository
from traffic_poc.tier1.bundle import import_bundle


def main() -> None:
    parser = argparse.ArgumentParser(description="Import unverified Tier-1 events")
    parser.add_argument("bundle", type=Path)
    args = parser.parse_args()
    settings = Settings.from_env()
    ids = import_bundle(args.bundle, settings, Repository(settings.data_dir))
    print(json.dumps({"record_ids": ids, "status": "awaiting_review"}, indent=2))


if __name__ == "__main__":
    main()
