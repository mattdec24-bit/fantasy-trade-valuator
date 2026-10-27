"""Explicit bundled import root, used with Python isolated mode (-I)."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import desktop
try:
    desktop.main()
except Exception:
    raise SystemExit(1) from None
