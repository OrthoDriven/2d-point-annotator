#!/usr/bin/env python3

"""
Cross-platform updater for 2D Point Annotator.
Runs outside the app directory to safely replace it.
"""

import json
import os
import shutil
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# ============================================================================
# Configuration (loaded from app.env or defaults)
# ============================================================================


def load_config():
    """Load configuration from app.env file."""
    script_dir = Path(__file__).parent
    install_root = script_dir.parent
    env_file = install_root / "app.env"

    config = {
        "INSTALL_ROOT": str(install_root),
        "APP_DIR": str(install_root / "app"),
        "STATE_PATH": str(install_root / "update_state.json"),
        "USER_AGENT": "2d-point-annotator-updater",
        "MIN_CHECK_INTERVAL_SECONDS": 15,
        "REQUEST_TIMEOUT_SEC": 15,
    }

    if env_file.exists():
        with open(env_file, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    value = value.strip().strip('"')
                    config[key] = value

    return config


# ============================================================================
# State Management
# ============================================================================


def load_state(state_path):
    """Load update state from JSON file."""
    if not Path(state_path).exists():
        return {
            "sha": "",
            "etag": "",
            "updatedUtc": datetime.now(timezone.utc).isoformat(),
            "lastCheckUtc": "1970-01-01T00:00:00Z",
        }

    try:
        with open(state_path, "r") as f:
            return json.load(f)
    except Exception:
        return {
            "sha": "",
            "etag": "",
            "updatedUtc": datetime.now(timezone.utc).isoformat(),
            "lastCheckUtc": "1970-01-01T00:00:00Z",
        }


def save_state(state_path, sha="", etag="", update_last_check=True):
    """Save update state to JSON file."""
    state = load_state(state_path)

    if sha:
        state["sha"] = sha
    if etag:
        state["etag"] = etag
    if update_last_check:
        state["lastCheckUtc"] = datetime.now(timezone.utc).isoformat()
    if sha or etag:
        state["updatedUtc"] = datetime.now(timezone.utc).isoformat()

    with open(state_path, "w") as f:
        json.dump(state, f, indent=2)


# ============================================================================
# GitHub API
# ============================================================================


def check_for_updates(api_url, state, user_agent, timeout):
    """Check GitHub API for new commits."""
    headers = {"User-Agent": user_agent}

    if state.get("etag"):
        headers["If-None-Match"] = state["etag"]

    request = Request(api_url, headers=headers)

    try:
        with urlopen(request, timeout=timeout) as response:
            etag = response.headers.get("ETag", "")
            data = json.loads(response.read().decode())

            # Handle both single commit and array responses
            if isinstance(data, list):
                data = data[0] if data else {}

            return {"status": "new", "sha": data.get("sha", ""), "etag": etag}
    except HTTPError as e:
        if e.code == 304:
            return {"status": "unchanged"}
        print(f"[warn] GitHub API error: HTTP {e.code}")
        return {"status": "error"}
    except URLError as e:
        print(f"[warn] Network error: {e.reason}")
        return {"status": "error"}
    except Exception as e:
        print(f"[warn] Unexpected error: {e}")
        return {"status": "error"}


# ============================================================================
# Download & Extract
# ============================================================================


def download_zip(url, dest_path, user_agent, timeout):
    """Download repository ZIP file."""
    headers = {"User-Agent": user_agent}
    request = Request(url, headers=headers)

    with urlopen(request, timeout=timeout) as response:
        with open(dest_path, "wb") as f:
            shutil.copyfileobj(response, f)


def find_project_root(extract_dir):
    """Find the directory containing pixi.toml in extracted archive."""
    for root, dirs, files in os.walk(extract_dir):
        if "pixi.toml" in files:
            return Path(root)
    return None


# ============================================================================
# Atomic Swap
# ============================================================================


def atomic_swap(new_dir, app_dir):
    """
    Atomically replace app directory with new version.
    Uses rename operations for atomicity on same filesystem.
    """
    app_path = Path(app_dir)
    new_path = app_path.parent / "app.new"
    old_path = app_path.parent / "app.old"

    # Clean up any leftover temp directories
    if new_path.exists():
        shutil.rmtree(new_path)
    if old_path.exists():
        shutil.rmtree(old_path)

    # Move new version to staging area
    shutil.move(str(new_dir), str(new_path))

    try:
        # Atomic swap using rename
        if app_path.exists():
            app_path.rename(old_path)
        new_path.rename(app_path)

        # Clean up old version
        if old_path.exists():
            shutil.rmtree(old_path)
    except Exception as e:
        # Rollback on failure
        print(f"[error] Swap failed: {e}")
        if not app_path.exists() and old_path.exists():
            try:
                old_path.rename(app_path)
            except Exception:
                pass
        if new_path.exists():
            shutil.rmtree(new_path)
        raise


# ============================================================================
# Main Update Logic
# ============================================================================


def should_check_for_updates(state, min_interval):
    """Determine if enough time has passed since last check."""
    try:
        last_check = datetime.fromisoformat(
            state["lastCheckUtc"].replace("Z", "+00:00")
        )
        now = datetime.now(timezone.utc)
        delta = (now - last_check).total_seconds()

        print(f"[debug] lastCheckUtc = {state['lastCheckUtc']}")
        print(f"[debug] now          = {now.isoformat()}")
        print(f"[debug] delta        = {delta:.1f} seconds")
        print(f"[debug] min interval = {min_interval} seconds")

        if delta < 0:
            print("[warn] lastCheckUtc is in the future; resetting")
            return True, 0

        if delta < min_interval:
            remaining = min_interval - delta
            print(
                f"[info] Skipping update check ({delta:.1f}s since last, {remaining:.1f}s remaining)"
            )
            return False, delta

        return True, delta
    except Exception as e:
        print(f"[warn] Could not parse lastCheckUtc: {e}")
        return True, 0


def run_update():
    """Main update routine."""
    config = load_config()
    state_path = config["STATE_PATH"]
    app_dir = config["APP_DIR"]

    # Load state
    state = load_state(state_path)

    # Check if we should run
    should_check, delta = should_check_for_updates(
        state, int(config["MIN_CHECK_INTERVAL_SECONDS"])
    )

    if not should_check:
        return

    # Always update lastCheckUtc from here on
    try:
        # Check for updates
        result = check_for_updates(
            config["API_URL"],
            state,
            config["USER_AGENT"],
            int(config["REQUEST_TIMEOUT_SEC"]),
        )

        save_state(state_path, update_last_check=True)

        if result["status"] == "error":
            return

        if result["status"] == "unchanged":
            print(f"[info] Already up-to-date ({state.get('sha', 'unknown')})")
            return

        new_sha = result.get("sha", "")
        if not new_sha:
            print("[warn] GitHub response did not include sha")
            return

        if state.get("sha") == new_sha:
            print(f"[info] Already up-to-date ({new_sha})")
            save_state(state_path, etag=result.get("etag", state.get("etag", "")))
            return

        print(f"[info] New version detected ({new_sha}). Updating...")

        # Download and extract
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            zip_path = temp_path / "annotator.zip"

            download_zip(
                config["REPO_ZIP_URL"],
                zip_path,
                config["USER_AGENT"],
                int(config["REQUEST_TIMEOUT_SEC"]) * 6,
            )

            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                zip_ref.extractall(temp_path)

            project_root = find_project_root(temp_path)
            if not project_root:
                print("[error] Cannot find project root in downloaded archive")
                return

            # Atomic swap
            atomic_swap(project_root, app_dir)

        # Update state
        save_state(state_path, sha=new_sha, etag=result.get("etag", ""))
        print(f"[info] Update complete -> {new_sha}")

    except Exception as e:
        print(f"[error] Update failed: {e}")
        save_state(state_path, update_last_check=True)
        raise


if __name__ == "__main__":
    try:
        run_update()
    except KeyboardInterrupt:
        print("\n[info] Update cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"[error] {e}")
        sys.exit(1)
