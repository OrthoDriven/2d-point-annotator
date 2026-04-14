import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from download_graph import (
    DownloadError,
    _download_folder_recursive,
    _download_one,
    download_graph,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_file_item(name: str, item_id: str | None = None):
    item = MagicMock()
    item.name = name
    item.id = item_id or f"id-{name}"
    item.folder = None
    item.file = MagicMock()
    return item


def _make_folder_item(name: str):
    item = MagicMock()
    item.name = name
    item.id = f"id-{name}"
    item.folder = MagicMock()
    item.file = None
    return item


def _make_client_for_content():
    """Mock client that only needs .drives...content.get() for downloads."""
    client = MagicMock()
    content_mock = MagicMock()
    content_mock.get = AsyncMock(return_value=b"file-content")
    (
        client.drives.by_drive_id.return_value.items.by_drive_item_id.return_value.content
    ) = content_mock
    return client


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_download_graph_auth_failure(tmp_path):
    """Verify that auth failure is wrapped in DownloadError."""
    with patch("download_graph.get_graph_client") as mock_auth:
        mock_auth.side_effect = Exception("Auth failed")
        with pytest.raises(DownloadError, match="Auth failed"):
            download_graph(
                drive_id="fake-drive",
                folder_path="/fake",
                dest_dir=tmp_path / "out",
            )


def test_download_one_writes_file(tmp_path):
    """_download_one fetches content and writes it to disk."""
    client = _make_client_for_content()
    item = _make_file_item("photo.tif")
    file_count = [0]

    asyncio.run(
        _download_one(
            client, "drv", item, tmp_path, asyncio.Semaphore(4), None, file_count
        )
    )

    assert file_count[0] == 1
    assert (tmp_path / "photo.tif").read_bytes() == b"file-content"


def test_download_one_reports_progress(tmp_path):
    """_download_one calls on_progress with the file name."""
    client = _make_client_for_content()
    item = _make_file_item("img.tif")
    msgs: list[str] = []

    asyncio.run(
        _download_one(
            client, "drv", item, tmp_path, asyncio.Semaphore(4), msgs.append, [0]
        )
    )

    assert len(msgs) == 1
    assert "img.tif" in msgs[0]


def test_download_concurrent_via_gather(tmp_path):
    """Multiple _download_one calls run concurrently under a semaphore."""
    client = _make_client_for_content()
    files = [_make_file_item(f"img{i}.tif") for i in range(5)]
    file_count = [0]
    sem = asyncio.Semaphore(8)

    async def _go():
        await asyncio.gather(
            *(
                _download_one(client, "drv", f, tmp_path, sem, None, file_count)
                for f in files
            )
        )

    asyncio.run(_go())

    assert file_count[0] == 5
    for i in range(5):
        assert (tmp_path / f"img{i}.tif").exists()


def test_download_folder_recursive_with_mock_list(tmp_path):
    """_download_folder_recursive lists children, downloads files, recurses folders."""
    # Patch _list_children to avoid real SDK class instantiation
    f_root = _make_file_item("root.tif")
    sub = _make_folder_item("sub")
    f_sub = _make_file_item("nested.tif")

    async def fake_list_children(client, drive_id, item_path):
        mapping = {
            "root:/top:": [sub, f_root],
            "root:/top/sub:": [f_sub],
        }
        return mapping.get(item_path, [])

    client = _make_client_for_content()
    file_count = [0]

    async def _go():
        sem = asyncio.Semaphore(8)
        with patch("download_graph._list_children", side_effect=fake_list_children):
            await _download_folder_recursive(
                client,
                "drv",
                "top",
                tmp_path,
                None,
                file_count,
                sem,
            )

    asyncio.run(_go())

    assert file_count[0] == 2
    assert (tmp_path / "root.tif").read_bytes() == b"file-content"
    assert (tmp_path / "sub" / "nested.tif").read_bytes() == b"file-content"


def test_download_folder_recursive_pagination_via_list(tmp_path):
    """Verifies that all items from _list_children (simulating pagination) are downloaded."""
    # _list_children returns items from multiple "pages" as a flat list
    all_files = [_make_file_item(f"f{i}.tif") for i in range(7)]

    async def fake_list_children(client, drive_id, item_path):
        return all_files

    client = _make_client_for_content()
    file_count = [0]

    async def _go():
        sem = asyncio.Semaphore(8)
        with patch("download_graph._list_children", side_effect=fake_list_children):
            await _download_folder_recursive(
                client,
                "drv",
                "data",
                tmp_path,
                None,
                file_count,
                sem,
            )

    asyncio.run(_go())

    assert file_count[0] == 7
    for i in range(7):
        assert (tmp_path / f"f{i}.tif").exists()
