#!/usr/bin/env python3
"""
External-user backup via Azure Function proxy.

External collaborators (no Microsoft account) upload annotation files
through an HTTP endpoint.  The Function holds the client secret server-side;
the desktop app only needs a per-user API key.

Configuration (highest priority first):
  1. Environment variables  ANNOTATOR_FUNCTION_URL, ANNOTATOR_API_KEY
  2. Config file  <AUTH_DIR>/external_config.json
  3. Interactive dialog on first use

Dev mode  (ANNOTATOR_DEV_MODE=1):
  Files are copied to <AUTH_DIR>/dev_uploads/ instead of calling Azure.
  Use this to exercise the external code path without any cloud resources.

Local emulator (ANNOTATOR_FUNCTION_URL=http://localhost:7071/api/upload):
  Point at a locally-running Azure Functions Core Tools instance.
"""

from __future__ import annotations

import getpass
import json
import logging
import os
import shutil
import sys
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import ttk
from typing import Callable, Optional, Sequence

import requests

sys.path.insert(0, str(Path(__file__).parents[1]))

from dirs import AUTH_DIR

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Defaults (override with env vars or config file)
# ---------------------------------------------------------------------------

# The URL of the Azure Function that proxies uploads.
# Replace this with your deployed function URL before distributing.
_DEFAULT_FUNCTION_URL = "https://REPLACE-ME.azurewebsites.net/api/upload"

_EXTERNAL_CONFIG_FILE = AUTH_DIR / "external_config.json"
DEV_UPLOAD_DIR = AUTH_DIR / "dev_uploads"


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------


def _load_config_file() -> dict:
    if _EXTERNAL_CONFIG_FILE.exists():
        try:
            return json.loads(_EXTERNAL_CONFIG_FILE.read_text())
        except Exception as e:
            logger.warning("Failed to read external_config.json: %s", e)
    return {}


def _save_config_file(data: dict) -> None:
    _EXTERNAL_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    _EXTERNAL_CONFIG_FILE.write_text(json.dumps(data, indent=2))


def get_function_url() -> str:
    """Return the Azure Function URL (env > config file > default)."""
    return (
        os.getenv("ANNOTATOR_FUNCTION_URL")
        or _load_config_file().get("function_url")
        or _DEFAULT_FUNCTION_URL
    )


def get_api_key() -> Optional[str]:
    """Return the saved API key (env > config file), or None."""
    return os.getenv("ANNOTATOR_API_KEY") or _load_config_file().get("api_key")


def save_api_key(api_key: str, function_url: Optional[str] = None) -> None:
    """Persist the API key (and optionally the function URL) to config."""
    data = _load_config_file()
    data["api_key"] = api_key
    if function_url:
        data["function_url"] = function_url
    _save_config_file(data)
    logger.info("External config saved")


def clear_external_config() -> None:
    """Remove the external config file (forces re-prompt on next run)."""
    if _EXTERNAL_CONFIG_FILE.exists():
        _EXTERNAL_CONFIG_FILE.unlink()


def is_dev_mode() -> bool:
    return os.getenv("ANNOTATOR_DEV_MODE", "").lower() in ("1", "true", "yes")


# ---------------------------------------------------------------------------
# API-key prompt dialog
# ---------------------------------------------------------------------------

_api_key_dialog: Optional[tk.Toplevel] = None


def show_api_key_dialog() -> Optional[str]:
    """
    Show a dialog asking for the per-user API key.
    Returns the entered key, or None if cancelled.
    """
    global _api_key_dialog

    result: list[Optional[str]] = [None]
    done = threading.Event()

    def _build_and_run():
        global _api_key_dialog

        try:
            root = getattr(tk, "_default_root", None)
            if root is None:
                root = tk.Tk()
                root.withdraw()
        except Exception:
            root = tk.Tk()
            root.withdraw()

        dialog = tk.Toplevel(root)
        _api_key_dialog = dialog

        dialog.title("External Collaborator — API Key")
        dialog.geometry("460x220")
        dialog.resizable(False, False)
        dialog.attributes("-topmost", True)

        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() - 460) // 2
        y = (dialog.winfo_screenheight() - 220) // 2
        dialog.geometry(f"460x220+{x}+{y}")

        def _on_close():
            result[0] = None
            done.set()
            dialog.destroy()

        dialog.protocol("WM_DELETE_WINDOW", _on_close)

        frame = ttk.Frame(dialog, padding=20)
        frame.pack(fill="both", expand=True)

        ttk.Label(
            frame,
            text="Enter the API key provided by your administrator:",
            font=("Helvetica", 11),
            wraplength=420,
            justify="left",
        ).pack(anchor="w", pady=(0, 10))

        key_var = tk.StringVar()
        entry = ttk.Entry(frame, textvariable=key_var, width=50, show="")
        entry.pack(anchor="w", pady=(0, 4))
        entry.focus_set()

        error_var = tk.StringVar()
        error_label = ttk.Label(
            frame, textvariable=error_var, foreground="red", font=("Helvetica", 9)
        )
        error_label.pack(anchor="w")

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(side="bottom", fill="x", pady=(12, 0))

        def _on_ok():
            key = key_var.get().strip()
            if not key:
                error_var.set("API key cannot be empty.")
                dialog.update()
                return
            result[0] = key
            done.set()
            dialog.destroy()

        def _on_cancel():
            result[0] = None
            done.set()
            dialog.destroy()

        ttk.Button(btn_frame, text="Save", command=_on_ok).pack(
            side="right", padx=(6, 0)
        )
        ttk.Button(btn_frame, text="Cancel", command=_on_cancel).pack(side="right")

        dialog.lift()
        dialog.focus_force()
        dialog.update()

    if threading.current_thread() is threading.main_thread():
        _build_and_run()
        while not done.is_set():
            try:
                root = getattr(tk, "_default_root", None)
                if root:
                    root.update()
                    root.after(50)
            except Exception:
                break
    else:
        try:
            root = getattr(tk, "_default_root", None)
            if root:
                root.after(0, _build_and_run)
            else:
                _build_and_run()
        except Exception:
            _build_and_run()

        done.wait(timeout=300)

    _api_key_dialog = None
    return result[0]


# ---------------------------------------------------------------------------
# Dev-mode upload
# ---------------------------------------------------------------------------


def _dev_upload(local_path: Path) -> bool:
    """Copy file to DEV_UPLOAD_DIR instead of calling Azure."""
    try:
        DEV_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        username = _get_username()
        date = datetime.now().strftime("%Y-%m-%d")
        dest_dir = DEV_UPLOAD_DIR / username / date
        dest_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(local_path, dest_dir / local_path.name)
        logger.info("[DEV] Copied %s → %s", local_path.name, dest_dir)
        return True
    except Exception as e:
        logger.error("[DEV] Copy failed: %s", e)
        return False


def _get_username() -> str:
    try:
        return getpass.getuser()
    except (KeyError, OSError):
        return os.getenv("USER") or os.getenv("USERNAME") or "default_user"


# ---------------------------------------------------------------------------
# Main uploader class
# ---------------------------------------------------------------------------


class FunctionProxyUploader:
    """
    Backup files via an Azure Function proxy endpoint.

    Implements the same interface as OneDriveBackup so it can be used as a
    drop-in replacement inside UnifiedBackup.

    Protocol
    --------
    POST {function_url}
      Header  X-API-Key: <api_key>
      Header  X-Username: <local username>
      Header  X-Filename: <filename>
      Body    raw file bytes

    The function echoes {"status": "ok"} on success.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._api_key: Optional[str] = None
        self._configured = False

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def _ensure_configured(self) -> bool:
        """Resolve API key, prompting once if not set. Returns True if ready."""
        if self._configured:
            return True

        with self._lock:
            if self._configured:
                return True

            if is_dev_mode():
                # In dev mode no real key is needed
                self._api_key = os.getenv("ANNOTATOR_API_KEY", "dev-api-key")
                self._configured = True
                logger.info("[DEV] External uploader configured (dev mode)")
                return True

            # Check env / config file
            api_key = get_api_key()
            if not api_key:
                logger.info("No API key found — prompting user")
                api_key = show_api_key_dialog()
                if not api_key:
                    logger.warning("User cancelled API key prompt")
                    return False
                # Persist
                save_api_key(api_key)

            self._api_key = api_key
            self._configured = True
            logger.info("External uploader configured")
            return True

    # Matches OneDriveBackup._ensure_initialized signature
    def _ensure_initialized(self) -> bool:
        return self._ensure_configured()

    # ------------------------------------------------------------------
    # Upload helpers
    # ------------------------------------------------------------------

    def _do_upload(self, local_path: Path, timeout: float = 30.0) -> bool:
        if is_dev_mode():
            return _dev_upload(local_path)

        api_key = self._api_key
        if not api_key:
            logger.error("Upload called but no API key is set")
            return False

        function_url = get_function_url()
        if "REPLACE-ME" in function_url:
            logger.error(
                "Function URL has not been configured. "
                "Set ANNOTATOR_FUNCTION_URL or update auth/external.py."
            )
            return False

        try:
            with open(local_path, "rb") as f:
                file_bytes = f.read()

            username = _get_username()
            headers = {
                "X-API-Key": api_key,
                "X-Username": username,
                "X-Filename": local_path.name,
                "Content-Type": "application/octet-stream",
            }

            response = requests.put(
                function_url,
                data=file_bytes,
                headers=headers,
                timeout=timeout,
            )

            if response.ok:
                logger.info("Uploaded %s via function proxy", local_path.name)
                return True
            else:
                logger.error(
                    "Function proxy returned %s: %s",
                    response.status_code,
                    response.text[:200],
                )
                return False

        except requests.Timeout:
            logger.warning("Upload timed out after %.1fs for %s", timeout, local_path)
            return False
        except Exception as e:
            logger.error("Upload error for %s: %s", local_path, e, exc_info=True)
            return False

    # ------------------------------------------------------------------
    # Public interface (mirrors OneDriveBackup)
    # ------------------------------------------------------------------

    def upload_backup_sync(
        self, file_path: "str | Path", timeout: float = 30.0
    ) -> bool:
        """Upload a file synchronously. Returns True on success."""
        path = Path(file_path)
        if not path.exists():
            logger.warning("File does not exist: %s", path)
            return False

        if not self._ensure_configured():
            return False

        return self._do_upload(path, timeout=timeout)

    def upload_backup(
        self,
        file_path: "str | Path",
        callback: Optional[Callable[[bool], None]] = None,
    ) -> None:
        """Upload a file in a background thread. Non-blocking."""
        path = Path(file_path)
        if not path.exists():
            logger.warning("File does not exist: %s", path)
            if callback:
                callback(False)
            return

        def _run():
            success = self.upload_backup_sync(path)
            if callback:
                callback(success)

        threading.Thread(target=_run, daemon=True).start()

    def backup_multiple(
        self,
        file_paths: "Sequence[str | Path]",
        callback: Optional[Callable[[int, int], None]] = None,
    ) -> None:
        """Backup multiple files in a background thread."""

        def _run():
            success_count = 0
            total = len(file_paths)
            for p in file_paths:
                path = Path(p)
                if path.exists() and self.upload_backup_sync(path):
                    success_count += 1
            if callback:
                callback(success_count, total)

        threading.Thread(target=_run, daemon=True).start()
