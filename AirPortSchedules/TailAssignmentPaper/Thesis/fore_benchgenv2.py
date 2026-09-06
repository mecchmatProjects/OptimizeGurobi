"""Compatibility wrapper for the migrated fore-benchgen implementation.

The maintained implementation is in ``src/fore_benchgen_impl.py``. This module
keeps the former thesis-path invocation available for existing scripts and notes.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "src"
if str(SOURCE_DIR) not in sys.path:
    sys.path.insert(0, str(SOURCE_DIR))

from fore_benchgen_impl import *


if __name__ == "__main__":
    raise SystemExit(main())
