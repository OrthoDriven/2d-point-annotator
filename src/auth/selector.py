#!/usr/bin/env python3
"""
User-type selection and persistence for 2D Point Annotator auth.

Tracks whether this install is used by an internal user (has a Microsoft /
ODI account) or an external collaborator (no Microsoft account, uses an
API key to upload through the Azure Function proxy).

The choice is stored in <AUTH_DIR>/user_type.json so the dialog is only
shown once per machine.
"""

from __future__ import annotations

import json
import logging
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Optional

sys.path.insert(0, str(Path(__file__).parents[1]))

from dirs import AUTH_DIR

logger = logging.getLogger(__name__)

USER_TYPE_INTERNAL = "internal"
USER_TYPE_EXTERNAL = "external"

_USER_TYPE_FILE = AUTH_DIR / "user_type.json"

# A global placeholder so dialogs created from background threads stay alive
_selector_dialog: Optional[tk.Toplevel] = None


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def get_saved_user_type() -> Optional[str]:
    """Return the saved user type ('internal' / 'external') or None."""
    if _USER_TYPE_FILE.exists():
        try:
            data = json.loads(_USER_TYPE_FILE.read_text())
            t = data.get("user_type")
            if t in (USER_TYPE_INTERNAL, USER_TYPE_EXTERNAL):
                return t
        except Exception as e:
            logger.warning("Failed to read user_type.json: %s", e)
    return None


def save_user_type(user_type: str) -> None:
    """Persist user type so the dialog is skipped on future launches."""
    _USER_TYPE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _USER_TYPE_FILE.write_text(json.dumps({"user_type": user_type}))
    logger.info("User type saved: %s", user_type)


def clear_user_type() -> None:
    """Remove persisted user type (forces the selector dialog next run)."""
    if _USER_TYPE_FILE.exists():
        _USER_TYPE_FILE.unlink()


# ---------------------------------------------------------------------------
# Dialog
# ---------------------------------------------------------------------------


def show_user_type_dialog() -> Optional[str]:
    """
    Show a Tkinter dialog asking whether the user has a Microsoft account.

    Returns 'internal', 'external', or None if the dialog was cancelled.

    Thread-safe: can be called from background threads (uses threading.Event
    to wait for the main-thread dialog to complete).
    """
    global _selector_dialog

    result: list[Optional[str]] = [None]
    done = threading.Event()

    def _build_and_run():
        global _selector_dialog

        try:
            root = getattr(tk, "_default_root", None)
            if root is None:
                root = tk.Tk()
                root.withdraw()
        except Exception:
            root = tk.Tk()
            root.withdraw()

        dialog = tk.Toplevel(root)
        _selector_dialog = dialog

        dialog.title("Sign-in Method")
        dialog.geometry("480x280")
        dialog.resizable(False, False)
        dialog.attributes("-topmost", True)

        # Center
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() - 480) // 2
        y = (dialog.winfo_screenheight() - 280) // 2
        dialog.geometry(f"480x280+{x}+{y}")

        # Prevent accidental close from cancelling silently
        def _on_close():
            result[0] = None
            done.set()
            dialog.destroy()

        dialog.protocol("WM_DELETE_WINDOW", _on_close)

        frame = ttk.Frame(dialog, padding=24)
        frame.pack(fill="both", expand=True)

        ttk.Label(
            frame,
            text="How would you like to back up your annotations?",
            font=("Helvetica", 13, "bold"),
            wraplength=430,
            justify="left",
        ).pack(anchor="w", pady=(0, 18))

        chosen = tk.StringVar(value="")

        internal_rb = ttk.Radiobutton(
            frame,
            text="I have a Microsoft / ODI account  (staff, students)",
            variable=chosen,
            value=USER_TYPE_INTERNAL,
        )
        internal_rb.pack(anchor="w", pady=4)

        external_rb = ttk.Radiobutton(
            frame,
            text="I'm an external collaborator  (no Microsoft account — use API key)",
            variable=chosen,
            value=USER_TYPE_EXTERNAL,
        )
        external_rb.pack(anchor="w", pady=4)

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(side="bottom", fill="x", pady=(18, 0))

        def _on_continue():
            t = chosen.get()
            if not t:
                # Nothing selected yet — flash a reminder
                ttk.Label(
                    frame, text="Please select an option.", foreground="red"
                ).pack()
                dialog.update()
                return
            result[0] = t
            done.set()
            dialog.destroy()

        def _on_cancel():
            result[0] = None
            done.set()
            dialog.destroy()

        ttk.Button(btn_frame, text="Continue", command=_on_continue).pack(
            side="right", padx=(6, 0)
        )
        ttk.Button(btn_frame, text="Cancel", command=_on_cancel).pack(side="right")

        dialog.lift()
        dialog.focus_force()
        dialog.update()

    # If we're already on the main Tk thread, just build synchronously
    if threading.current_thread() is threading.main_thread():
        _build_and_run()
        # Spin the event loop until the dialog is dismissed
        while not done.is_set():
            try:
                root = getattr(tk, "_default_root", None)
                if root:
                    root.update()
                    root.after(50)
            except Exception:
                break
    else:
        # Schedule on the main thread and wait
        try:
            root = getattr(tk, "_default_root", None)
            if root:
                root.after(0, _build_and_run)
            else:
                _build_and_run()
        except Exception:
            _build_and_run()

        # Wait up to 5 minutes for user to respond
        done.wait(timeout=300)

    _selector_dialog = None
    return result[0]
