from __future__ import annotations

import pathlib
import sys

# Allow importing tap_bench without requiring package installation.
ROOT = pathlib.Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
REPO_ROOT = ROOT.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tap_bench.cli.main import main


if __name__ == "__main__":
    main()
