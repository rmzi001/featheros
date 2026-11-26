"""Test package bootstrap ensuring compat/ is importable."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
COMPAT = ROOT / "compat"
if str(COMPAT) not in sys.path:
    sys.path.insert(0, str(COMPAT))
