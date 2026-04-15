#!/usr/bin/env python3
"""
auth package for 2D Point Annotator.

Public API is backward-compatible with the old auth.py module.
New entry point: create_backup_manager() — returns a UnifiedBackup that asks
users whether they have a Microsoft account and routes accordingly.

Internal users  → OneDriveBackup  (device-code flow, unchanged)
External users  → FunctionProxyUploader  (Azure Function + API key)
"""

from __future__ import annotations

import logging
import threading
from typing import Callable, Optional, Sequence
from pathlib import Path

# Re-export everything that tests / main.py currently import from auth.py
from auth.internal import (
    AUTH_RECORD_PATH,
    BASE_BACKUP_FOLDER,
    SHAREPOINT_DRIVE_ID,
    OneDriveBackup,
    get_backup_instance,
    get_date_folder,
    get_graph_client,
    get_safe_username,
)
from auth.external import FunctionProxyUploader
import auth.selector as _selector  # module reference so tests can monkeypatch it
from auth.selector import (
    USER_TYPE_EXTERNAL,
    USER_TYPE_INTERNAL,
    clear_user_type,
    get_saved_user_type,
    save_user_type,
    show_user_type_dialog,
)

logger = logging.getLogger(__name__)

__all__ = [
    # Backward-compat re-exports
    "AUTH_RECORD_PATH",
    "BASE_BACKUP_FOLDER",
    "SHAREPOINT_DRIVE_ID",
    "OneDriveBackup",
    "get_backup_instance",
    "get_date_folder",
    "get_graph_client",
    "get_safe_username",
    # External path
    "FunctionProxyUploader",
    # Selector
    "USER_TYPE_INTERNAL",
    "USER_TYPE_EXTERNAL",
    "get_saved_user_type",
    "save_user_type",
    "clear_user_type",
    "show_user_type_dialog",
    # New unified entry point
    "UnifiedBackup",
    "create_backup_manager",
    # Old convenience helper — kept for compat
    "backup_to_onedrive",
]


# ---------------------------------------------------------------------------
# UnifiedBackup
# ---------------------------------------------------------------------------


class UnifiedBackup:
    """
    Backup manager that picks the right implementation on first use.

    First call to any upload method:
      1. Reads saved user type from disk.
      2. If not set, shows the 'Internal / External' selector dialog.
      3. Delegates to OneDriveBackup (internal) or FunctionProxyUploader (external).

    Drop-in replacement for OneDriveBackup — same interface.
    """

    def __init__(self) -> None:
        self._delegate: Optional[OneDriveBackup | FunctionProxyUploader] = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_delegate(self) -> Optional[OneDriveBackup | FunctionProxyUploader]:
        if self._delegate is not None:
            return self._delegate

        with self._lock:
            if self._delegate is not None:
                return self._delegate

            # Call through module reference so tests can monkeypatch these
            user_type = _selector.get_saved_user_type()
            if user_type is None:
                user_type = _selector.show_user_type_dialog()
                if user_type is None:
                    logger.warning("User cancelled auth type selection")
                    return None
                _selector.save_user_type(user_type)

            if user_type == USER_TYPE_INTERNAL:
                logger.info("Using internal (Microsoft account) backup path")
                self._delegate = OneDriveBackup()
            else:
                logger.info("Using external (function proxy) backup path")
                self._delegate = FunctionProxyUploader()

            return self._delegate

    # ------------------------------------------------------------------
    # Public interface (mirrors OneDriveBackup)
    # ------------------------------------------------------------------

    def _ensure_initialized(self) -> bool:
        delegate = self._get_delegate()
        if delegate is None:
            return False
        return delegate._ensure_initialized()

    def upload_backup_sync(
        self, file_path: "str | Path", timeout: float = 30.0
    ) -> bool:
        delegate = self._get_delegate()
        if delegate is None:
            return False
        return delegate.upload_backup_sync(file_path, timeout)

    def upload_backup(
        self,
        file_path: "str | Path",
        callback: Optional[Callable[[bool], None]] = None,
    ) -> None:
        delegate = self._get_delegate()
        if delegate is None:
            if callback:
                callback(False)
            return
        delegate.upload_backup(file_path, callback)

    def backup_multiple(
        self,
        file_paths: "Sequence[str | Path]",
        callback: Optional[Callable[[int, int], None]] = None,
    ) -> None:
        delegate = self._get_delegate()
        if delegate is None:
            if callback:
                callback(0, len(file_paths))
            return
        delegate.backup_multiple(file_paths, callback)


# ---------------------------------------------------------------------------
# Factory & convenience helper
# ---------------------------------------------------------------------------


def create_backup_manager() -> UnifiedBackup:
    """Return a new UnifiedBackup instance."""
    return UnifiedBackup()


# Kept for backward compatibility (old auth.py had this)
_backup_instance: Optional[UnifiedBackup] = None


def backup_to_onedrive(
    file_path: "str | Path",
    callback: Optional[Callable[[bool], None]] = None,
) -> None:
    """
    Convenience wrapper — kept for backward compatibility.
    New code should use create_backup_manager() instead.
    """
    global _backup_instance
    if _backup_instance is None:
        _backup_instance = UnifiedBackup()
    instance = _backup_instance
    instance.upload_backup(file_path, callback)
