from __future__ import annotations

import os
from pathlib import Path


def local_state_dir() -> Path:
    return Path(os.environ.get("FULCRUM_LOCAL_STATE_DIR", "/var/lib/fulcrum/local"))
