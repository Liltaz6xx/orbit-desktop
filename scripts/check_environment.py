"""Compatibility entry point for the ORBIT system check."""

import sys
from pathlib import Path

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from orbit.diagnostics import main

    sys.exit(main())
