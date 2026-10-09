#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""specdex: read-only search and maintenance checks for BMAD specifications.

Run `uv run scripts/specdex.py --help` (or `python3 scripts/specdex.py --help`).
"""
import signal
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # never leave __pycache__ inside an installed skill folder
if hasattr(signal, "SIGPIPE"):
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)  # `specdex … | head` ends quietly instead of with a traceback
sys.path.insert(0, str(Path(__file__).resolve().parent))

from specdexlib.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
