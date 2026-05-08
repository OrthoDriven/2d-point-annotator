import logging
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Callable, Optional

import requests

logger = logging.getLogger(__name__)


class DownloadError(Exception):
    """Raised when the download or extraction step fails."""


def download_zip(
    url: str,
    dest_dir: Path,
    on_progress: Optional[Callable[[str], None]] = None,
    skip_existing: bool = False,
) -> None:
    def report(msg: str) -> None:
        if on_progress is not None:
            on_progress(msg)

    report("Connecting…")
    try:
        with requests.get(url, stream=True, timeout=60) as resp:
            resp.raise_for_status()
            total = int(resp.headers.get("content-length", 0) or 0)
            downloaded = 0
            buf = BytesIO()
            for chunk in resp.iter_content(chunk_size=65536):
                if chunk:
                    buf.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        pct = int(downloaded * 100 / total)
                        report(f"Downloading… {pct}%")
                    else:
                        mb = downloaded / 1048576
                        report(f"Downloading… {mb:.1f} MB")
    except Exception as exc:
        raise DownloadError(str(exc)) from exc

    dest_dir.mkdir(parents=True, exist_ok=True)
    buf.seek(0)

    if zipfile.is_zipfile(buf):
        buf.seek(0)
        report("Extracting…")
        with zipfile.ZipFile(buf) as zf:
            members = zf.namelist()
            prefix = ""
            if members:
                tops = {m.split("/")[0] for m in members}
                if len(tops) == 1:
                    prefix = tops.pop() + "/"
            dest_resolved = dest_dir.resolve()
            for member in members:
                stripped = member[len(prefix) :] if prefix else member
                if not stripped:
                    continue
                target = dest_dir / stripped
                # Zip Slip guard: ensure resolved path stays inside dest_dir
                if not target.resolve().is_relative_to(dest_resolved):
                    logger.warning("Skipping path traversal entry: %s", member)
                    continue
                if member.endswith("/"):
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    if skip_existing and target.exists():
                        continue
                    # Also guard parent directory creation
                    parent_resolved = target.parent.resolve()
                    if not parent_resolved.is_relative_to(dest_resolved):
                        logger.warning("Skipping traversal in parent of: %s", member)
                        continue
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(member) as src, open(target, "wb") as dst:
                        dst.write(src.read())
    else:
        buf.seek(0)
        report("Saving…")
        (dest_dir / "data_package").write_bytes(buf.read())

    report("Done.")
