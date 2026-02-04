#!/usr/bin/env python3
import platform
from pathlib import Path

BASE_DIR = Path(__file__).parents[1]
APP_DIR = BASE_DIR.parent
BASE_DIR_PATH = Path(BASE_DIR)
DATA_DIR = APP_DIR / "data"
AUTH_DIR = APP_DIR / "auth"
PLATFORM = platform.system()
