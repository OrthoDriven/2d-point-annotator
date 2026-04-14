import asyncio
from pathlib import Path
from typing import Callable, Optional
from auth import get_graph_client


class DownloadError(Exception):
    """Raised when the Graph API download fails."""


async def _download_folder_recursive(
    client,
    drive_id: str,
    folder_path: str,
    dest_dir: Path,
    on_progress: Optional[Callable[[str], None]],
    file_count: list[int],
) -> None:
    item_path = f"root:/{folder_path.strip('/')}:"
    children = await (
        client.drives.by_drive_id(drive_id)
        .items.by_drive_item_id(item_path)
        .children.get()
    )

    if not children or not children.value:
        return

    for item in children.value:
        if item.folder:
            await _download_folder_recursive(
                client,
                drive_id,
                f"{folder_path}/{item.name}",
                dest_dir / item.name,
                on_progress,
                file_count,
            )
        elif item.file:
            file_count[0] += 1
            if on_progress:
                on_progress(f"Downloading file {file_count[0]}: {item.name}…")
            content = await (
                client.drives.by_drive_id(drive_id)
                .items.by_drive_item_id(item.id)
                .content.get()
            )
            dest_dir.mkdir(parents=True, exist_ok=True)
            (dest_dir / item.name).write_bytes(content)


def download_graph(
    drive_id: str,
    folder_path: str,
    dest_dir: Path,
    on_progress: Optional[Callable[[str], None]] = None,
) -> None:
    try:
        if on_progress:
            on_progress("Authenticating…")
        client = get_graph_client()

        if on_progress:
            on_progress("Listing files…")

        # Use SelectorEventLoop to avoid Windows ProactorEventLoop hangs
        # (same pattern as auth.py upload_backup_sync)
        loop = asyncio.SelectorEventLoop()
        file_count = [0]
        try:
            loop.run_until_complete(
                _download_folder_recursive(
                    client,
                    drive_id,
                    folder_path,
                    dest_dir,
                    on_progress,
                    file_count,
                )
            )
        finally:
            loop.close()

        if on_progress:
            on_progress(f"Done. {file_count[0]} files downloaded.")
    except DownloadError:
        raise
    except Exception as e:
        raise DownloadError(str(e)) from e
