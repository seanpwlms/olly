"""Remove all generated files from the dev demo.

Usage:
    uv run python dev/clean_demo.py
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

# Ensure the project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from olly.state import get_olly_dir

DEV_DIR = Path(__file__).resolve().parent

CLEANUP = [
    get_olly_dir(),
    DEV_DIR / "warehouse.duckdb",
    DEV_DIR / "warehouse.duckdb.wal",
    DEV_DIR / "source.duckdb",
    DEV_DIR / "source.duckdb.wal",
    DEV_DIR / "target.duckdb",
    DEV_DIR / "target.duckdb.wal",
]


def main() -> None:
    for path in CLEANUP:
        if path.is_dir():
            shutil.rmtree(path)
            print(f"  removed {path.relative_to(DEV_DIR)}/")
        elif path.exists():
            path.unlink()
            print(f"  removed {path.relative_to(DEV_DIR)}")

    print("Clean.")


if __name__ == "__main__":
    main()
