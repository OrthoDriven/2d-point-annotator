#!/usr/bin/env python3
"""
Tests for the external-user authentication path.

These tests cover FunctionProxyUploader and UnifiedBackup without any real
Azure resources by using dev mode (ANNOTATOR_DEV_MODE=1).

Run with:
    pixi run python -m pytest tests/test_external_auth.py -v -s

All tests are fully offline — no network calls, no Tkinter dialogs.
"""

import json
import sys
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from auth.external import (
    DEV_UPLOAD_DIR,
    FunctionProxyUploader,
    _EXTERNAL_CONFIG_FILE,
    clear_external_config,
    get_api_key,
    get_function_url,
    is_dev_mode,
    save_api_key,
)
from auth.selector import (
    USER_TYPE_EXTERNAL,
    USER_TYPE_INTERNAL,
    _USER_TYPE_FILE,
    clear_user_type,
    get_saved_user_type,
    save_user_type,
)
from auth import UnifiedBackup


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolate_config(tmp_path, monkeypatch):
    """
    Redirect all config files to a temp directory so tests don't touch
    real user state, and enable dev mode so no network calls happen.

    Also blocks Tkinter dialogs by default — tests that specifically test
    dialog behavior must override show_user_type_dialog / show_api_key_dialog
    via their own monkeypatch calls.
    """
    fake_auth = tmp_path / "auth"
    fake_auth.mkdir()

    monkeypatch.setenv("ANNOTATOR_DEV_MODE", "1")
    monkeypatch.setenv("ANNOTATOR_API_KEY", "test-api-key-123")

    import auth.external as ext_mod
    import auth.selector as sel_mod

    monkeypatch.setattr(ext_mod, "_EXTERNAL_CONFIG_FILE", fake_auth / "external_config.json")
    monkeypatch.setattr(ext_mod, "DEV_UPLOAD_DIR", fake_auth / "dev_uploads")
    monkeypatch.setattr(sel_mod, "_USER_TYPE_FILE", fake_auth / "user_type.json")

    # Block all Tkinter dialogs by default — no headless display in CI.
    # Tests that need to test dialog flow should provide their own mock.
    monkeypatch.setattr(sel_mod, "show_user_type_dialog", lambda: None)
    monkeypatch.setattr(ext_mod, "show_api_key_dialog", lambda: None)

    yield


@pytest.fixture
def temp_annotation_file(tmp_path):
    """Create a small fake annotation file."""
    f = tmp_path / "annotations_test.json"
    f.write_text(json.dumps({"image": "hip.png", "landmarks": {"L-LIP": [100, 200]}}))
    return f


# ---------------------------------------------------------------------------
# Dev-mode detection
# ---------------------------------------------------------------------------


class TestDevMode:
    def test_dev_mode_on(self, monkeypatch):
        monkeypatch.setenv("ANNOTATOR_DEV_MODE", "1")
        assert is_dev_mode() is True

    def test_dev_mode_true_string(self, monkeypatch):
        monkeypatch.setenv("ANNOTATOR_DEV_MODE", "true")
        assert is_dev_mode() is True

    def test_dev_mode_off_by_default(self, monkeypatch):
        monkeypatch.delenv("ANNOTATOR_DEV_MODE", raising=False)
        assert is_dev_mode() is False

    def test_dev_mode_empty_string(self, monkeypatch):
        monkeypatch.setenv("ANNOTATOR_DEV_MODE", "")
        assert is_dev_mode() is False


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------


class TestConfigHelpers:
    def test_save_and_load_api_key(self, tmp_path, monkeypatch):
        import auth.external as ext_mod
        cfg = tmp_path / "cfg.json"
        monkeypatch.setattr(ext_mod, "_EXTERNAL_CONFIG_FILE", cfg)
        monkeypatch.delenv("ANNOTATOR_API_KEY", raising=False)

        save_api_key("my-secret-key")
        assert get_api_key() == "my-secret-key"

    def test_env_var_overrides_file(self, monkeypatch):
        monkeypatch.setenv("ANNOTATOR_API_KEY", "env-key")
        assert get_api_key() == "env-key"

    def test_env_var_overrides_function_url(self, monkeypatch):
        monkeypatch.setenv("ANNOTATOR_FUNCTION_URL", "https://custom.example.com/api/upload")
        assert get_function_url() == "https://custom.example.com/api/upload"

    def test_clear_config(self, tmp_path, monkeypatch):
        import auth.external as ext_mod
        cfg = tmp_path / "cfg.json"
        monkeypatch.setattr(ext_mod, "_EXTERNAL_CONFIG_FILE", cfg)
        monkeypatch.delenv("ANNOTATOR_API_KEY", raising=False)

        save_api_key("some-key")
        assert cfg.exists()
        clear_external_config()
        assert not cfg.exists()


# ---------------------------------------------------------------------------
# User type selector persistence
# ---------------------------------------------------------------------------


class TestUserTypeSelector:
    def test_no_type_initially(self):
        assert get_saved_user_type() is None

    def test_save_and_load_internal(self):
        save_user_type(USER_TYPE_INTERNAL)
        assert get_saved_user_type() == USER_TYPE_INTERNAL

    def test_save_and_load_external(self):
        save_user_type(USER_TYPE_EXTERNAL)
        assert get_saved_user_type() == USER_TYPE_EXTERNAL

    def test_clear_restores_none(self):
        save_user_type(USER_TYPE_INTERNAL)
        clear_user_type()
        assert get_saved_user_type() is None

    def test_invalid_value_returns_none(self, tmp_path, monkeypatch):
        import auth.selector as sel_mod
        f = tmp_path / "user_type.json"
        f.write_text(json.dumps({"user_type": "BOGUS"}))
        monkeypatch.setattr(sel_mod, "_USER_TYPE_FILE", f)
        assert get_saved_user_type() is None


# ---------------------------------------------------------------------------
# FunctionProxyUploader — dev mode uploads
# ---------------------------------------------------------------------------


class TestFunctionProxyUploaderDevMode:
    """Tests that run in dev mode (writes to disk, no network)."""

    def test_upload_sync_success(self, temp_annotation_file, monkeypatch):
        import auth.external as ext_mod
        dev_dir = temp_annotation_file.parent / "dev_uploads"
        monkeypatch.setattr(ext_mod, "DEV_UPLOAD_DIR", dev_dir)

        uploader = FunctionProxyUploader()
        result = uploader.upload_backup_sync(temp_annotation_file, timeout=5.0)

        assert result is True
        # File should have been copied somewhere under dev_dir
        uploaded = list(dev_dir.rglob(temp_annotation_file.name))
        assert len(uploaded) == 1

    def test_upload_nonexistent_file(self, tmp_path):
        uploader = FunctionProxyUploader()
        result = uploader.upload_backup_sync(tmp_path / "ghost.json", timeout=5.0)
        assert result is False

    def test_upload_async_with_callback(self, temp_annotation_file, monkeypatch):
        import auth.external as ext_mod
        dev_dir = temp_annotation_file.parent / "dev_uploads"
        monkeypatch.setattr(ext_mod, "DEV_UPLOAD_DIR", dev_dir)

        uploader = FunctionProxyUploader()
        done = threading.Event()
        results = []

        def on_done(ok):
            results.append(ok)
            done.set()

        uploader.upload_backup(temp_annotation_file, callback=on_done)
        assert done.wait(timeout=10.0), "Async upload did not complete in 10s"
        assert results == [True]

    def test_backup_multiple(self, tmp_path, monkeypatch):
        import auth.external as ext_mod
        dev_dir = tmp_path / "dev_uploads"
        monkeypatch.setattr(ext_mod, "DEV_UPLOAD_DIR", dev_dir)

        files = []
        for i in range(3):
            f = tmp_path / f"file_{i}.json"
            f.write_text(json.dumps({"idx": i}))
            files.append(f)

        uploader = FunctionProxyUploader()
        done = threading.Event()
        counts = []

        def on_done(success, total):
            counts.append((success, total))
            done.set()

        uploader.backup_multiple(files, callback=on_done)
        assert done.wait(timeout=15.0), "backup_multiple did not complete in 15s"
        assert counts == [(3, 3)]

    def test_ensure_initialized_returns_true_in_dev(self):
        uploader = FunctionProxyUploader()
        assert uploader._ensure_initialized() is True


# ---------------------------------------------------------------------------
# FunctionProxyUploader — production path (mocked HTTP)
# ---------------------------------------------------------------------------


class TestFunctionProxyUploaderHTTP:
    """Tests the real HTTP path with a mocked requests.put."""

    @pytest.fixture(autouse=True)
    def _no_dev_mode(self, monkeypatch):
        monkeypatch.setenv("ANNOTATOR_DEV_MODE", "0")
        monkeypatch.setenv(
            "ANNOTATOR_FUNCTION_URL",
            "https://test-function.azurewebsites.net/api/upload",
        )
        monkeypatch.setenv("ANNOTATOR_API_KEY", "real-api-key")

    def test_successful_upload(self, temp_annotation_file):
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.status_code = 200

        with patch("auth.external.requests.put", return_value=mock_resp) as mock_put:
            uploader = FunctionProxyUploader()
            result = uploader.upload_backup_sync(temp_annotation_file, timeout=10.0)

        assert result is True
        mock_put.assert_called_once()
        call_kwargs = mock_put.call_args
        assert call_kwargs.kwargs["headers"]["X-API-Key"] == "real-api-key"
        assert call_kwargs.kwargs["headers"]["X-Filename"] == temp_annotation_file.name

    def test_server_error_returns_false(self, temp_annotation_file):
        mock_resp = MagicMock()
        mock_resp.ok = False
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"

        with patch("auth.external.requests.put", return_value=mock_resp):
            uploader = FunctionProxyUploader()
            result = uploader.upload_backup_sync(temp_annotation_file, timeout=10.0)

        assert result is False

    def test_network_timeout_returns_false(self, temp_annotation_file):
        import requests as req_mod

        with patch("auth.external.requests.put", side_effect=req_mod.Timeout):
            uploader = FunctionProxyUploader()
            result = uploader.upload_backup_sync(temp_annotation_file, timeout=5.0)

        assert result is False

    def test_placeholder_url_returns_false(self, temp_annotation_file, monkeypatch):
        """If the function URL was never configured, fail gracefully."""
        monkeypatch.delenv("ANNOTATOR_FUNCTION_URL", raising=False)
        import auth.external as ext_mod
        monkeypatch.setattr(ext_mod, "_DEFAULT_FUNCTION_URL", "https://REPLACE-ME.azurewebsites.net/api/upload")

        uploader = FunctionProxyUploader()
        result = uploader.upload_backup_sync(temp_annotation_file, timeout=5.0)
        assert result is False


# ---------------------------------------------------------------------------
# UnifiedBackup — routing logic (no Tk dialogs)
# ---------------------------------------------------------------------------


class TestUnifiedBackupRouting:
    """Test that UnifiedBackup picks the right delegate based on saved user type."""

    def test_routes_to_function_proxy_when_external(self, monkeypatch):
        import auth.selector as sel_mod
        monkeypatch.setattr(sel_mod, "get_saved_user_type", lambda: USER_TYPE_EXTERNAL)

        ub = UnifiedBackup()
        delegate = ub._get_delegate()
        assert isinstance(delegate, FunctionProxyUploader)

    def test_routes_to_onedrive_when_internal(self, monkeypatch):
        from auth import OneDriveBackup
        import auth.selector as sel_mod
        monkeypatch.setattr(sel_mod, "get_saved_user_type", lambda: USER_TYPE_INTERNAL)

        ub = UnifiedBackup()
        delegate = ub._get_delegate()
        assert isinstance(delegate, OneDriveBackup)

    def test_returns_none_when_cancelled(self, monkeypatch):
        import auth.selector as sel_mod
        monkeypatch.setattr(sel_mod, "get_saved_user_type", lambda: None)
        monkeypatch.setattr(sel_mod, "show_user_type_dialog", lambda: None)

        ub = UnifiedBackup()
        delegate = ub._get_delegate()
        assert delegate is None

    def test_upload_returns_false_when_no_delegate(self, tmp_path, monkeypatch):
        import auth.selector as sel_mod
        monkeypatch.setattr(sel_mod, "get_saved_user_type", lambda: None)
        monkeypatch.setattr(sel_mod, "show_user_type_dialog", lambda: None)

        f = tmp_path / "test.json"
        f.write_text("{}")
        ub = UnifiedBackup()
        assert ub.upload_backup_sync(f) is False

    def test_saves_user_type_on_first_select(self, monkeypatch):
        import auth.selector as sel_mod
        saved = []
        monkeypatch.setattr(sel_mod, "get_saved_user_type", lambda: None)
        monkeypatch.setattr(
            sel_mod, "show_user_type_dialog", lambda: USER_TYPE_EXTERNAL
        )
        monkeypatch.setattr(sel_mod, "save_user_type", lambda t: saved.append(t))

        ub = UnifiedBackup()
        ub._get_delegate()
        assert saved == [USER_TYPE_EXTERNAL]

    def test_delegate_cached_after_first_call(self, monkeypatch):
        """_get_delegate should not call the dialog a second time."""
        import auth.selector as sel_mod
        call_count = [0]

        def _mock_dialog():
            call_count[0] += 1
            return USER_TYPE_EXTERNAL

        monkeypatch.setattr(sel_mod, "get_saved_user_type", lambda: None)
        monkeypatch.setattr(sel_mod, "show_user_type_dialog", _mock_dialog)
        monkeypatch.setattr(sel_mod, "save_user_type", lambda t: None)

        ub = UnifiedBackup()
        ub._get_delegate()
        ub._get_delegate()
        assert call_count[0] == 1


# ---------------------------------------------------------------------------
# Integration: full external upload in dev mode
# ---------------------------------------------------------------------------


class TestExternalIntegration:
    """End-to-end external path using dev mode (disk only)."""

    def test_full_flow_external_dev(self, tmp_path, monkeypatch):
        import auth.selector as sel_mod
        import auth.external as ext_mod

        dev_dir = tmp_path / "dev_uploads"
        monkeypatch.setattr(ext_mod, "DEV_UPLOAD_DIR", dev_dir)
        monkeypatch.setattr(sel_mod, "get_saved_user_type", lambda: USER_TYPE_EXTERNAL)

        # Create annotation file
        ann = tmp_path / "hip_landmarks.json"
        ann.write_text(json.dumps({"image": "hip.png"}))

        ub = UnifiedBackup()
        result = ub.upload_backup_sync(ann, timeout=10.0)

        assert result is True
        uploaded = list(dev_dir.rglob("hip_landmarks.json"))
        assert len(uploaded) == 1
        print(f"\n[TEST] Dev upload → {uploaded[0]}")


if __name__ == "__main__":
    import subprocess
    subprocess.run(
        ["python", "-m", "pytest", __file__, "-v", "-s"],
        cwd=Path(__file__).parent.parent,
    )
