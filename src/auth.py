#!/usr/bin/env python3

"""
OneDrive backup integration for 2D Point Annotator.
Provides authentication and file upload to SharePoint/OneDrive.

Usage:
    from auth import OneDriveBackup

    backup = OneDriveBackup()
    backup.upload_backup("/path/to/file.db")  # Uploads to user/date folder
"""

from __future__ import annotations

import asyncio
import getpass
import logging
import threading
import tkinter as tk
import webbrowser
from datetime import datetime
from pathlib import Path
from tkinter import font, ttk
from typing import Callable, Optional, Sequence

from azure.identity import (
    AuthenticationRecord,
    DeviceCodeCredential,
    TokenCachePersistenceOptions,
)
from msgraph import GraphServiceClient
from msgraph.generated.models.drive_item import DriveItem
from msgraph.generated.models.folder import Folder

from dirs import AUTH_DIR

logger = logging.getLogger(__name__)

# Azure AD app registration
CLIENT_ID = "d6a282f7-2887-4e76-b92c-e8ca63ea5c8b"
TENANT_ID = "f59bcc9c-bb13-4ca4-a6ec-ac126b6ec4b9"
SCOPES = ["Files.ReadWrite.All"]

# SharePoint drive ID for backup storage
SHAREPOINT_DRIVE_ID = (
    "b!KMPrFjP2-EyF3_IAVjRxqwRrQzp7wJ5Bj5GN_uL5GeVd5oQt5J70S4Ie1tl8qDeE"
)
BASE_BACKUP_FOLDER = "pelvic-2d-points-backup"

AUTH_RECORD_PATH = AUTH_DIR / "auth_record.json"

# Global reference to auth dialog (to prevent garbage collection)
_auth_dialog: Optional[tk.Toplevel] = None


def _show_auth_dialog(uri: str, code: str) -> None:
    """Show a Tkinter dialog with the authentication code."""
    global _auth_dialog

    # Try to get existing Tk root, or create temporary one
    try:
        # Access the default root (private attribute)
        root = getattr(tk, "_default_root", None)
        if root is None:
            # No Tk root exists yet - create a temporary hidden one
            root = tk.Tk()
            root.withdraw()
    except Exception:
        root = tk.Tk()
        root.withdraw()

    # Create dialog window
    dialog = tk.Toplevel(root)
    dialog.title("OneDrive Login Required")
    dialog.geometry("500x350")
    dialog.resizable(False, False)

    # Center on screen
    dialog.update_idletasks()
    x = (dialog.winfo_screenwidth() - 500) // 2
    y = (dialog.winfo_screenheight() - 350) // 2
    dialog.geometry(f"500x350+{x}+{y}")

    # Make it stay on top
    dialog.attributes("-topmost", True)
    dialog.lift()
    dialog.focus_force()

    # Main frame with padding
    frame = ttk.Frame(dialog, padding=20)
    frame.pack(fill="both", expand=True)

    # Title
    title_label = ttk.Label(
        frame,
        text="ONE-TIME LOGIN",
        font=("Helvetica", 18, "bold"),
    )
    title_label.pack(pady=(0, 15))

    # Instructions
    instructions = ttk.Label(
        frame,
        text="A browser window has opened.\nEnter this code to sign in:",
        font=font.nametofont("TkDefaultFont").copy().configure(size=28),
        justify="center",
    )
    instructions.pack(pady=(0, 20))

    # Code display (large, prominent)
    code_frame = ttk.Frame(frame)
    code_frame.pack(pady=10)

    code_label = ttk.Label(
        code_frame,
        text=code,
        font=font.nametofont("TkDefaultFont").copy().configure(size=36),
        foreground="#0066cc",
    )
    code_label.pack(padx=20, pady=15)

    # Copy button
    def copy_code():
        dialog.clipboard_clear()
        dialog.clipboard_append(code)
        copy_btn.config(text="Copied!")
        dialog.after(1500, lambda: copy_btn.config(text="Copy Code"))

    copy_btn = ttk.Button(
        frame,
        text="Copy Code",
        command=copy_code,
    )
    copy_btn.pack(pady=10)

    # URL info (smaller)
    url_label = ttk.Label(
        frame,
        text=f"URL: {uri}",
        font=("Helvetica", 9),
        foreground="gray",
    )
    url_label.pack(pady=(15, 0))

    # Note about closing
    note_label = ttk.Label(
        frame,
        text="This window will close automatically after login.",
        font=("Helvetica", 9, "italic"),
        foreground="gray",
    )
    note_label.pack(pady=(5, 0))

    # Store reference globally to prevent garbage collection
    _auth_dialog = dialog

    # Force update
    dialog.update()


def _close_auth_dialog() -> None:
    """Close the auth dialog if it exists."""
    global _auth_dialog
    if _auth_dialog is not None:
        try:
            _auth_dialog.destroy()
        except Exception:
            pass
        _auth_dialog = None


def _prompt_callback(uri: str, code: str, expires_on) -> None:
    """Display device code authentication prompt via Tkinter dialog."""
    # Open browser
    if uri:
        try:
            webbrowser.open(uri, new=2)
        except Exception:
            pass

    # Show Tkinter dialog with code
    try:
        _show_auth_dialog(uri, code)
    except Exception as e:
        # Fallback to console if Tkinter fails
        logger.warning(f"Failed to show auth dialog: {e}")
        print(f"\n{'=' * 60}")
        print("ONE-TIME LOGIN")
        print(f"Open: {uri}")
        print(f"\nENTER THIS CODE:\n\n    {code}\n")
        print("=" * 60)


def get_safe_username() -> str:
    """Get username for folder paths. Cross-platform safe."""
    try:
        return getpass.getuser()
    except (KeyError, OSError):
        import os

        return os.getenv("USER") or os.getenv("USERNAME") or "default_user"


def get_date_folder() -> str:
    """Get today's date as folder name (YYYY-MM-DD)."""
    return datetime.now().strftime("%Y-%m-%d")


class OneDriveBackup:
    """
    Manages OneDrive backup operations for annotation files.

    Uploads to: pelvic-2d-points-backup/<username>/<YYYY-MM-DD>/

    Thread-safe: upload operations run in background threads.
    """

    def __init__(self) -> None:
        self._client: Optional[GraphServiceClient] = None
        self._credential: Optional[DeviceCodeCredential] = None
        self._lock = threading.Lock()
        self._initialized = False

    def _ensure_initialized(self) -> bool:
        """Lazy initialization of Graph client. Returns True if ready."""
        if self._initialized:
            return True

        with self._lock:
            if self._initialized:
                return True

            try:
                # Load cached auth record if exists
                record = None
                if AUTH_RECORD_PATH.exists():
                    try:
                        record = AuthenticationRecord.deserialize(
                            AUTH_RECORD_PATH.read_text()
                        )
                    except Exception as e:
                        logger.warning(f"Failed to load auth record: {e}")

                # Setup credential with token cache
                cache_opts = TokenCachePersistenceOptions(
                    name="onedrive-ml", allow_unencrypted_storage=True
                )

                self._credential = DeviceCodeCredential(
                    client_id=CLIENT_ID,
                    tenant_id=TENANT_ID,
                    cache_persistence_options=cache_opts,
                    authentication_record=record,
                    prompt_callback=_prompt_callback,
                )

                # Authenticate if no cached record
                if record is None and self._credential is not None:
                    record = self._credential.authenticate(scopes=SCOPES)
                    AUTH_RECORD_PATH.parent.mkdir(parents=True, exist_ok=True)
                    AUTH_RECORD_PATH.write_text(record.serialize())
                    # Close the auth dialog after successful authentication
                    _close_auth_dialog()

                self._client = GraphServiceClient(
                    credentials=self._credential, scopes=SCOPES
                )
                self._initialized = True
                return True

            except Exception as e:
                logger.error(f"Failed to initialize OneDrive client: {e}")
                return False

    async def _ensure_folder_exists(self, folder_path: str) -> bool:
        """
        Ensure folder path exists, creating nested folders as needed.
        folder_path: e.g., "pelvic-2d-points-backup/username/2024-01-15"
        """
        if not self._client:
            return False

        parts = folder_path.strip("/").split("/")
        current_path = ""

        for part in parts:
            parent_path = current_path if current_path else "root"
            current_path = f"{current_path}/{part}" if current_path else part

            try:
                # Check if folder exists by trying to get it
                item_path = f"root:/{current_path}:" if current_path else "root"
                await (
                    self._client.drives.by_drive_id(SHAREPOINT_DRIVE_ID)
                    .items.by_drive_item_id(item_path)
                    .get()
                )
            except Exception:
                # Folder doesn't exist, create it
                try:
                    request_body = DriveItem(
                        name=part,
                        folder=Folder(),
                        additional_data={
                            "@microsoft.graph" + ".conflictBehavior": "fail"
                        },
                    )

                    parent_item_id = (
                        f"root:/{'/'.join(current_path.split('/')[:-1])}:"
                        if "/" in current_path
                        else "root"
                    )

                    await (
                        self._client.drives.by_drive_id(SHAREPOINT_DRIVE_ID)
                        .items.by_drive_item_id(parent_item_id)
                        .children.post(request_body)
                    )
                    logger.info(f"Created folder: {current_path}")
                except Exception as e:
                    # Might already exist due to race condition, continue
                    if "nameAlreadyExists" not in str(e):
                        logger.warning(f"Failed to create folder {current_path}: {e}")

        return True

    async def _upload_file_async(self, local_path: Path, remote_folder: str) -> bool:
        """Upload a file to the specified remote folder."""
        if not self._client:
            return False

        try:
            with open(local_path, "rb") as f:
                file_content = f.read()

            dest_file_name = local_path.name
            drive_item_path = f"root:/{remote_folder}/{dest_file_name}:"

            uploaded_file: Optional[DriveItem] = await (
                self._client.drives.by_drive_id(SHAREPOINT_DRIVE_ID)
                .items.by_drive_item_id(drive_item_path)
                .content.put(file_content)
            )

            if uploaded_file and uploaded_file.name:
                logger.info(f"Uploaded: {uploaded_file.name} to {remote_folder}")
                return True
            return False

        except Exception as e:
            logger.error(f"Failed to upload {local_path}: {e}")
            return False

    async def _backup_file_async(self, local_path: Path) -> bool:
        """
        Backup a file to OneDrive with user/date folder structure.

        Uploads to: pelvic-2d-points-backup/<username>/<YYYY-MM-DD>/<filename>
        """
        if not self._ensure_initialized():
            logger.error("OneDrive client not initialized")
            return False

        username = get_safe_username()
        date_folder = get_date_folder()
        remote_folder = f"{BASE_BACKUP_FOLDER}/{username}/{date_folder}"

        # Ensure folder structure exists
        await self._ensure_folder_exists(remote_folder)

        # Upload the file
        return await self._upload_file_async(local_path, remote_folder)

    def upload_backup(
        self, file_path: str | Path, callback: Optional[Callable[[bool], None]] = None
    ) -> None:
        """
        Upload a file to OneDrive backup in background thread.

        Args:
            file_path: Path to file to upload (db or csv)
            callback: Optional callback(success: bool) when complete

        Non-blocking - runs in background thread.
        """
        path = Path(file_path)
        if not path.exists():
            logger.warning(f"File does not exist: {path}")
            if callback:
                callback(False)
            return

        def _run():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                success = loop.run_until_complete(self._backup_file_async(path))
                loop.close()
                if callback:
                    callback(success)
            except Exception as e:
                logger.error(f"Backup thread error: {e}")
                if callback:
                    callback(False)

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()

    def upload_backup_sync(self, file_path: str | Path, timeout: float = 30.0) -> bool:
        """
        Upload a file to OneDrive backup synchronously with timeout.

        Use this for critical saves (e.g., on window close) where
        you need to ensure the upload completes before continuing.

        Args:
            file_path: Path to file to upload
            timeout: Maximum seconds to wait for upload (default 30s)

        Returns True on success, False on failure or timeout.
        """
        path = Path(file_path)
        if not path.exists():
            logger.warning(f"File does not exist: {path}")
            return False

        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            # Wrap the coroutine with a timeout
            coro = asyncio.wait_for(self._backup_file_async(path), timeout=timeout)
            success = loop.run_until_complete(coro)
            loop.close()
            return success
        except asyncio.TimeoutError:
            logger.error(f"Sync backup timed out after {timeout}s for {path}")
            return False
        except Exception as e:
            logger.error(f"Sync backup error: {e}")
            return False

    def backup_multiple(
        self,
        file_paths: Sequence[str | Path],
        callback: Optional[Callable[[int, int], None]] = None,
    ) -> None:
        """
        Backup multiple files in background.

        Args:
            file_paths: List of file paths to backup
            callback: Optional callback(success_count, total_count) when complete
        """

        def _run():
            success_count = 0
            total = len(file_paths)

            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

                for path in file_paths:
                    p = Path(path)
                    if p.exists():
                        if loop.run_until_complete(self._backup_file_async(p)):
                            success_count += 1

                loop.close()
            except Exception as e:
                logger.error(f"Multi-backup error: {e}")

            if callback:
                callback(success_count, total)

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()


# Convenience function for simple usage
_backup_instance: Optional[OneDriveBackup] = None


def get_backup_instance() -> OneDriveBackup:
    """Get or create the singleton backup instance."""
    global _backup_instance
    if _backup_instance is None:
        _backup_instance = OneDriveBackup()
    return _backup_instance


def backup_to_onedrive(
    file_path: str | Path, callback: Optional[Callable[[bool], None]] = None
) -> None:
    """
    Convenience function to backup a file to OneDrive.

    Usage:
        from auth import backup_to_onedrive
        backup_to_onedrive("/path/to/file.db")
    """
    get_backup_instance().upload_backup(file_path, callback)
