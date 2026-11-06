"""The repository root, for every file in tests/. Standard library only, so the
scripts here that plain python3 runs can import it too."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
