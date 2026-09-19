"""Prevent competing workers from recovering each other's live jobs."""

import os
from pathlib import Path


class RuntimeLease:
    """Hold an OS-managed lock for one pipeline per data directory."""

    def __init__(self, directory: Path):
        self.stream = (directory / ".runtime.lock").open("a+b")
        if self.stream.seek(0, os.SEEK_END) == 0:
            self.stream.write(b"\0")
            self.stream.flush()
        self.stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.stream.close()
            raise RuntimeError("Another pipeline is using this data directory") from exc

    def close(self) -> None:
        """Closing the descriptor releases the lock, including on process termination."""
        if not self.stream.closed:
            self.stream.close()
