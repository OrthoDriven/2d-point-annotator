import asyncio
from pathlib import Path
from typing import Callable, Optional

from auth import get_graph_client
from msgraph.generated.drives.item.items.item.children.children_request_builder import (
    ChildrenRequestBuilder,
)

# Max concurrent file downloads.  Graph API throttles around 10-20 concurrent
# requests per app; 8 keeps us safely under while still being much faster than
# sequential.
_MAX_CONCURRENT_DOWNLOADS = 8


class DownloadError(Exception):
    """Raised when the Graph API download fails."""


async def _list_children(client, drive_id: str, item_path: str) -> list:
    """List ALL children of a drive item, handling pagination.

    The Graph API returns at most ``$top`` items per page (default 200).
    We request pages of 1000 (the API maximum) and follow
    ``odata_next_link`` until all items are collected.
    """
    query_params = ChildrenRequestBuilder.ChildrenRequestBuilderGetQueryParameters(
        top=1000
    )
    request_config = (
        ChildrenRequestBuilder.ChildrenRequestBuilderGetRequestConfiguration(
            query_parameters=query_params,
        )
    )

    page = await (
        client.drives.by_drive_id(drive_id)
        .items.by_drive_item_id(item_path)
        .children.get(request_configuration=request_config)
    )

    items: list = []
    while page is not None:
        if page.value:
            items.extend(page.value)
        if not page.odata_next_link:
            break
        page = await (
            client.drives.by_drive_id(drive_id)
            .items.by_drive_item_id(item_path)
            .children.with_url(page.odata_next_link)
            .get()
        )

    return items


async def _download_one(
    client,
    drive_id: str,
    item,
    dest_dir: Path,
    sem: asyncio.Semaphore,
    on_progress: Optional[Callable[[str], None]],
    file_count: list[int],
) -> None:
    """Download a single file, respecting the concurrency semaphore."""
    async with sem:
        file_count[0] += 1
        if on_progress:
            on_progress(f"Downloading file {file_count[0]}: {item.name}\u2026")
        content = await (
            client.drives.by_drive_id(drive_id)
            .items.by_drive_item_id(item.id)
            .content.get()
        )
        dest_dir.mkdir(parents=True, exist_ok=True)
        (dest_dir / item.name).write_bytes(content)


async def _download_folder_recursive(
    client,
    drive_id: str,
    folder_path: str,
    dest_dir: Path,
    on_progress: Optional[Callable[[str], None]],
    file_count: list[int],
    sem: asyncio.Semaphore,
) -> None:
    item_path = f"root:/{folder_path.strip('/')}:"
    items = await _list_children(client, drive_id, item_path)

    if not items:
        return

    # Separate folders and files so we can download files concurrently
    folders = []
    files = []
    for item in items:
        if item.folder:
            folders.append(item)
        elif item.file:
            files.append(item)

    # Download files in this folder concurrently
    if files:
        await asyncio.gather(
            *(
                _download_one(
                    client, drive_id, f, dest_dir, sem, on_progress, file_count
                )
                for f in files
            )
        )

    # Recurse into subfolders (sequentially — each subfolder fans out its own
    # concurrent downloads, so we avoid an explosion of tasks)
    for folder in folders:
        await _download_folder_recursive(
            client,
            drive_id,
            f"{folder_path}/{folder.name}",
            dest_dir / folder.name,
            on_progress,
            file_count,
            sem,
        )


def download_graph(
    drive_id: str,
    folder_path: str,
    dest_dir: Path,
    on_progress: Optional[Callable[[str], None]] = None,
) -> None:
    try:
        if on_progress:
            on_progress("Authenticating\u2026")
        client = get_graph_client()

        if on_progress:
            on_progress("Listing files\u2026")

        # Use SelectorEventLoop to avoid Windows ProactorEventLoop hangs
        # (same pattern as auth.py upload_backup_sync)
        loop = asyncio.SelectorEventLoop()
        file_count = [0]
        sem = asyncio.Semaphore(_MAX_CONCURRENT_DOWNLOADS)
        try:
            loop.run_until_complete(
                _download_folder_recursive(
                    client,
                    drive_id,
                    folder_path,
                    dest_dir,
                    on_progress,
                    file_count,
                    sem,
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
