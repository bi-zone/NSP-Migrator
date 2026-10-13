import base64
import os
import sys
from pathlib import Path

os.environ.setdefault(
    "APP_CSP_MASTER_KEY",
    base64.b64encode(b"test-csp-master-key-material-32b").decode(),
)
os.environ.setdefault("APP_CSP_MASTER_KEY_ID", "test-v1")

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (SRC, ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
