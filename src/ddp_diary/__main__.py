"""Enables `python -m ddp_diary ...` as an install-free fallback to the
`ddp-diary` console script (spec.md §9)."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
