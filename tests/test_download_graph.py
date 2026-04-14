import sys
from pathlib import Path
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from download_graph import download_graph, DownloadError


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
