#!/usr/bin/env python3
"""Entry point for the msu.io NFT scraper."""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure local imports work when running ``python main.py``.
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scraper import main


if __name__ == "__main__":
    main()