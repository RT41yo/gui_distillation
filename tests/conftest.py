# tests/conftest.py
import sys
from pathlib import Path

# Add repo root to sys.path so imports like `from src...` work.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
