import sys
import zipfile
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from download_zip import DownloadError, download_zip


def test_download_zip_network_error():
    with patch("download_zip.requests.get") as mock_get:
        mock_get.side_effect = Exception("Network error")
        with pytest.raises(DownloadError, match="Network error"):
            download_zip("http://example.com/file.zip", Path("/tmp/dest"))


def _make_response(payload: bytes, content_length: int | None = None):
    response = MagicMock()
    response.__enter__.return_value = response
    response.__exit__.return_value = False
    response.raise_for_status.return_value = None
    response.iter_content.return_value = [payload]
    response.headers = {}
    if content_length is not None:
        response.headers["content-length"] = str(content_length)
    return response


def test_download_zip_extracts_zip(tmp_path: Path):
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("package/file.txt", "hello")
        zf.writestr("package/subdir/inner.txt", "world")
    response = _make_response(buf.getvalue(), content_length=len(buf.getvalue()))

    with patch("download_zip.requests.get", return_value=response):
        download_zip("http://example.com/file.zip", tmp_path)

    assert (tmp_path / "file.txt").read_text() == "hello"
    assert (tmp_path / "subdir" / "inner.txt").read_text() == "world"


def test_download_zip_saves_non_zip(tmp_path: Path):
    payload = b"not a zip"
    response = _make_response(payload, content_length=len(payload))

    with patch("download_zip.requests.get", return_value=response):
        download_zip("http://example.com/file.bin", tmp_path)

    assert (tmp_path / "data_package").read_bytes() == payload


def test_download_zip_reports_progress():
    payload = b"abc"
    response = _make_response(payload, content_length=3)
    messages: list[str] = []

    with patch("download_zip.requests.get", return_value=response):
        download_zip("http://example.com/file.bin", Path("/tmp/dest"), messages.append)

    assert messages[0] == "Connecting…"
    assert any(msg == "Downloading… 100%" for msg in messages)
    assert messages[-1] == "Done."
