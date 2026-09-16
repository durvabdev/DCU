"""Build a seeded SQLite snapshot for Vercel. The runtime copies it to /tmp."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT = ROOT / "data" / "vercel-seed.sqlite"


def main() -> int:
    SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    if SNAPSHOT.exists():
        SNAPSHOT.unlink()
    os.environ["DATABASE_URL"] = f"sqlite:///{SNAPSHOT}"
    from app.config import clear_settings_cache

    clear_settings_cache()
    from app.seed import main as seed_main

    return seed_main(["--quiet"])


if __name__ == "__main__":
    raise SystemExit(main())
