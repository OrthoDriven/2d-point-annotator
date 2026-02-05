#!/usr/bin/env python3
import json
import shutil
from pathlib import Path
from typing import Dict, List

import requests
from packaging.version import Version as V

REPO_URL = "https://api.github.com/repos/OrthoDriven/2d-point-annotator/releases"


def get_releases(url: str):
    r = requests.get(url)
    print(r.content)
    return r.json()


def download_release_zip(zip_url: str, download_path: Path) -> None:
    with requests.get(zip_url, stream=True) as r:
        with open(download_path, "wb") as f:
            f.write(r.content)


print(V("1.9.0") > V("1.2.0"))
