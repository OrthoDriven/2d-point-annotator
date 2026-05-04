"""
DEPRECATED: This module is replaced by src/auto_merge.py.

The per-file json_update_rules.json system has been replaced by a global
auto-merge that works for any JSON by filename matching against the repo's
data/ directory.

This stub is kept only to avoid import errors in case any code still
references it. All functions are no-ops.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def load_rules() -> List[Dict[str, Any]]:
    """Deprecated: rules system removed. Returns empty list."""
    return []


def check_and_apply_rules(
    current_json_path: Optional[Path] = None,
    annotator_name: Optional[str] = None,
    dry_run: bool = False,
) -> List[Dict[str, Any]]:
    """Deprecated: use auto_merge.auto_merge_on_load() instead."""
    logger.debug("json_updater.check_and_apply_rules called but is deprecated")
    return []


def get_pending_rules(
    current_json_path: Optional[Path] = None,
    annotator_name: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Deprecated: rules system removed. Returns empty list."""
    return []
