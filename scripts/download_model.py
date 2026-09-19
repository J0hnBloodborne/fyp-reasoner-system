"""Fetch only inference artifacts; do not load weights into VRAM."""

from huggingface_hub import snapshot_download

from traffic_poc.config import Settings


def main() -> None:
    settings = Settings.from_env()
    path = snapshot_download(
        settings.model_id,
        revision=settings.revision,
        cache_dir=str(settings.model_cache),
        max_workers=2,
        allow_patterns=["*.json", "*.safetensors", "*.jinja", "*.txt"],
        local_files_only=settings.offline,
    )
    print(f"Model snapshot ready: {path}")


if __name__ == "__main__":
    main()
