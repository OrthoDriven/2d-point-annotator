#!/usr/bin/env python3
"""
Tests for OneDrive backup functionality.

These tests verify:
1. Auth initialization (credential loading)
2. Fresh client creation per thread
3. Single file upload (sync and async)
4. Multiple file uploads
5. Timeout behavior
6. Thread safety

Run with: pixi run python -m pytest tests/test_onedrive_upload.py -v -s

The -s flag shows print output so you can see where things hang.
"""

import asyncio
import sys
import tempfile
import threading
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

import pytest

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from auth import (
    OneDriveBackup,
    get_safe_username,
    get_date_folder,
    AUTH_RECORD_PATH,
    BASE_BACKUP_FOLDER,
    SHAREPOINT_DRIVE_ID,
)


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def backup_instance():
    """Create a fresh OneDriveBackup instance for each test."""
    return OneDriveBackup()


@pytest.fixture
def temp_files(tmp_path):
    """Create temporary test files of various sizes."""
    files = {}

    # Small file (1KB)
    small = tmp_path / "small_test.txt"
    small.write_text("x" * 1024)
    files["small"] = small

    # Medium file (100KB)
    medium = tmp_path / "medium_test.txt"
    medium.write_text("y" * (100 * 1024))
    files["medium"] = medium

    # DB-like file (SQLite header + data)
    db_file = tmp_path / "test_annotations.db"
    # SQLite files start with this header
    db_file.write_bytes(b"SQLite format 3\x00" + b"\x00" * 100 + b"test data" * 1000)
    files["db"] = db_file

    # CSV-like file
    csv_file = tmp_path / "test_annotations.csv"
    csv_content = "image_path,landmark1,landmark2\n"
    for i in range(100):
        csv_content += f"/path/to/image_{i}.png,[{i}.0,{i}.0],[{i + 1}.0,{i + 1}.0]\n"
    csv_file.write_text(csv_content)
    files["csv"] = csv_file

    return files


# =============================================================================
# Basic Functionality Tests
# =============================================================================


class TestBasicFunctionality:
    """Test basic helper functions."""

    def test_get_safe_username(self):
        """Username should be a non-empty string."""
        username = get_safe_username()
        print(f"[TEST] Username: {username}")
        assert isinstance(username, str)
        assert len(username) > 0
        assert "/" not in username  # No path separators
        assert "\\" not in username

    def test_get_date_folder(self):
        """Date folder should be YYYY-MM-DD format."""
        date_folder = get_date_folder()
        print(f"[TEST] Date folder: {date_folder}")
        assert isinstance(date_folder, str)
        assert len(date_folder) == 10  # YYYY-MM-DD
        parts = date_folder.split("-")
        assert len(parts) == 3
        assert len(parts[0]) == 4  # Year
        assert len(parts[1]) == 2  # Month
        assert len(parts[2]) == 2  # Day


# =============================================================================
# Auth & Initialization Tests
# =============================================================================


class TestAuthInitialization:
    """Test authentication and client initialization."""

    def test_auth_record_path_exists(self):
        """Check if auth record exists (user must have authenticated previously)."""
        print(f"[TEST] Auth record path: {AUTH_RECORD_PATH}")
        print(f"[TEST] Auth record exists: {AUTH_RECORD_PATH.exists()}")
        # Don't assert - just informational

    def test_backup_instance_creation(self, backup_instance):
        """Creating OneDriveBackup should not block or hang."""
        print("[TEST] Creating OneDriveBackup instance...")
        assert backup_instance is not None
        assert backup_instance._client is None  # Lazy init
        assert backup_instance._initialized is False
        print("[TEST] Instance created successfully (not yet initialized)")

    def test_ensure_initialized_with_timeout(self, backup_instance):
        """_ensure_initialized should complete within timeout."""
        print("[TEST] Testing _ensure_initialized with 10s timeout...")

        result = [None]
        error = [None]

        def init_thread():
            try:
                result[0] = backup_instance._ensure_initialized()
            except Exception as e:
                error[0] = e

        thread = threading.Thread(target=init_thread)
        thread.start()
        thread.join(timeout=10.0)

        if thread.is_alive():
            print("[TEST] FAILED: _ensure_initialized hung for >10s")
            pytest.fail("_ensure_initialized hung - thread still alive after 10s")

        if error[0]:
            print(f"[TEST] _ensure_initialized raised: {error[0]}")

        print(f"[TEST] _ensure_initialized returned: {result[0]}")
        # Result may be True or False depending on auth state

    def test_fresh_client_creation(self, backup_instance):
        """_create_fresh_client should work or fail gracefully."""
        print("[TEST] Testing _create_fresh_client...")

        # First ensure we have auth
        backup_instance._ensure_initialized()

        client = backup_instance._create_fresh_client()
        print(f"[TEST] Fresh client created: {client is not None}")
        # Client may be None if no auth record exists


# =============================================================================
# Upload Tests (require valid auth)
# =============================================================================


class TestUploads:
    """Test upload functionality. Requires valid OneDrive auth."""

    @pytest.fixture(autouse=True)
    def check_auth(self, backup_instance):
        """Skip upload tests if not authenticated."""
        if not AUTH_RECORD_PATH.exists():
            pytest.skip("No auth record - run the app first to authenticate")

    def test_upload_small_file_sync(self, backup_instance, temp_files):
        """Upload a small file synchronously with timeout."""
        print("\n[TEST] === Testing small file sync upload ===")
        small_file = temp_files["small"]
        print(f"[TEST] File: {small_file} ({small_file.stat().st_size} bytes)")

        # Use ThreadPoolExecutor to enforce overall timeout
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                backup_instance.upload_backup_sync, small_file, timeout=30.0
            )
            try:
                result = future.result(timeout=35.0)  # Extra 5s for overhead
                print(f"[TEST] Upload result: {result}")
                assert isinstance(result, bool)
            except FuturesTimeoutError:
                print("[TEST] FAILED: Upload hung beyond 35s total timeout")
                pytest.fail("Upload hung - exceeded 35s total timeout")

    def test_upload_db_file_sync(self, backup_instance, temp_files):
        """Upload a DB-like file synchronously."""
        print("\n[TEST] === Testing DB file sync upload ===")
        db_file = temp_files["db"]
        print(f"[TEST] File: {db_file} ({db_file.stat().st_size} bytes)")

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                backup_instance.upload_backup_sync, db_file, timeout=30.0
            )
            try:
                result = future.result(timeout=35.0)
                print(f"[TEST] Upload result: {result}")
                assert isinstance(result, bool)
            except FuturesTimeoutError:
                print("[TEST] FAILED: DB upload hung beyond 35s")
                pytest.fail("DB upload hung")

    def test_upload_csv_file_sync(self, backup_instance, temp_files):
        """Upload a CSV file synchronously."""
        print("\n[TEST] === Testing CSV file sync upload ===")
        csv_file = temp_files["csv"]
        print(f"[TEST] File: {csv_file} ({csv_file.stat().st_size} bytes)")

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                backup_instance.upload_backup_sync, csv_file, timeout=30.0
            )
            try:
                result = future.result(timeout=35.0)
                print(f"[TEST] Upload result: {result}")
                assert isinstance(result, bool)
            except FuturesTimeoutError:
                print("[TEST] FAILED: CSV upload hung beyond 35s")
                pytest.fail("CSV upload hung")

    def test_upload_nonexistent_file(self, backup_instance, tmp_path):
        """Uploading nonexistent file should return False immediately."""
        print("\n[TEST] === Testing nonexistent file upload ===")
        fake_file = tmp_path / "does_not_exist.txt"
        print(f"[TEST] File: {fake_file} (exists: {fake_file.exists()})")

        result = backup_instance.upload_backup_sync(fake_file, timeout=5.0)
        print(f"[TEST] Upload result: {result}")
        assert result is False


# =============================================================================
# Async Upload Tests
# =============================================================================


class TestAsyncUploads:
    """Test async/callback-based uploads."""

    @pytest.fixture(autouse=True)
    def check_auth(self):
        if not AUTH_RECORD_PATH.exists():
            pytest.skip("No auth record - run the app first to authenticate")

    def test_upload_async_with_callback(self, backup_instance, temp_files):
        """Test async upload with callback."""
        print("\n[TEST] === Testing async upload with callback ===")
        small_file = temp_files["small"]

        callback_called = threading.Event()
        callback_result = [None]

        def on_complete(success):
            print(f"[TEST] Callback received: success={success}")
            callback_result[0] = success
            callback_called.set()

        print(f"[TEST] Starting async upload of {small_file}")
        backup_instance.upload_backup(small_file, callback=on_complete)

        # Wait for callback with timeout
        if callback_called.wait(timeout=35.0):
            print(f"[TEST] Async upload completed: {callback_result[0]}")
            assert isinstance(callback_result[0], bool)
        else:
            print("[TEST] FAILED: Async upload callback not received in 35s")
            pytest.fail("Async upload timed out")

    def test_backup_multiple_files(self, backup_instance, temp_files):
        """Test backing up multiple files at once."""
        print("\n[TEST] === Testing multiple file backup ===")
        files = [temp_files["small"], temp_files["csv"]]

        callback_called = threading.Event()
        callback_result = [None, None]

        def on_complete(success_count, total):
            print(f"[TEST] Multi-backup callback: {success_count}/{total}")
            callback_result[0] = success_count
            callback_result[1] = total
            callback_called.set()

        print(f"[TEST] Starting backup of {len(files)} files")
        backup_instance.backup_multiple(files, callback=on_complete)

        if callback_called.wait(timeout=60.0):
            print(
                f"[TEST] Multi-backup completed: {callback_result[0]}/{callback_result[1]}"
            )
            assert callback_result[1] == len(files)
        else:
            print("[TEST] FAILED: Multi-backup callback not received in 60s")
            pytest.fail("Multi-backup timed out")


# =============================================================================
# Thread Safety Tests
# =============================================================================


class TestThreadSafety:
    """Test thread safety of upload operations."""

    @pytest.fixture(autouse=True)
    def check_auth(self):
        if not AUTH_RECORD_PATH.exists():
            pytest.skip("No auth record - run the app first to authenticate")

    def test_concurrent_uploads_different_threads(self, temp_files):
        """Test uploading from multiple threads simultaneously."""
        print("\n[TEST] === Testing concurrent uploads from different threads ===")

        results = {}
        errors = {}

        def upload_in_thread(name, file_path):
            print(f"[TEST] Thread {name} starting upload of {file_path.name}")
            # Each thread gets its own backup instance
            backup = OneDriveBackup()
            try:
                result = backup.upload_backup_sync(file_path, timeout=30.0)
                results[name] = result
                print(f"[TEST] Thread {name} completed: {result}")
            except Exception as e:
                errors[name] = e
                print(f"[TEST] Thread {name} error: {e}")

        threads = [
            threading.Thread(target=upload_in_thread, args=("A", temp_files["small"])),
            threading.Thread(target=upload_in_thread, args=("B", temp_files["csv"])),
        ]

        print("[TEST] Starting threads...")
        for t in threads:
            t.start()

        print("[TEST] Waiting for threads (max 45s each)...")
        for t in threads:
            t.join(timeout=45.0)
            if t.is_alive():
                print(f"[TEST] WARNING: Thread still alive after 45s")

        print(f"[TEST] Results: {results}")
        print(f"[TEST] Errors: {errors}")

        # At least check we didn't deadlock
        assert len(results) + len(errors) == 2, "Not all threads completed"


# =============================================================================
# Timeout Behavior Tests
# =============================================================================


class TestTimeoutBehavior:
    """Test that timeouts work correctly."""

    def test_very_short_timeout(self, backup_instance, temp_files):
        """Test that a very short timeout actually times out."""
        print("\n[TEST] === Testing very short timeout (0.001s) ===")

        if not AUTH_RECORD_PATH.exists():
            pytest.skip("No auth record")

        small_file = temp_files["small"]

        start = time.time()
        result = backup_instance.upload_backup_sync(small_file, timeout=0.001)
        elapsed = time.time() - start

        print(f"[TEST] Result: {result}, elapsed: {elapsed:.3f}s")
        # Should either timeout quickly or fail quickly
        assert elapsed < 5.0, "Short timeout took too long to fail"


# =============================================================================
# Standalone Test Runner
# =============================================================================

if __name__ == "__main__":
    """Run tests directly without pytest for quick debugging."""
    print("=" * 70)
    print("OneDrive Upload Tests - Direct Runner")
    print("=" * 70)

    # Run a simple test sequence
    print("\n1. Testing get_safe_username...")
    username = get_safe_username()
    print(f"   Username: {username}")

    print("\n2. Testing get_date_folder...")
    date = get_date_folder()
    print(f"   Date folder: {date}")

    print("\n3. Checking auth record...")
    print(f"   Path: {AUTH_RECORD_PATH}")
    print(f"   Exists: {AUTH_RECORD_PATH.exists()}")

    if not AUTH_RECORD_PATH.exists():
        print("\n[SKIP] No auth record found. Run the app to authenticate first.")
        sys.exit(0)

    print("\n4. Creating OneDriveBackup instance...")
    backup = OneDriveBackup()
    print("   Created (not yet initialized)")

    print("\n5. Testing _ensure_initialized (10s timeout)...")
    init_done = threading.Event()
    init_result = [None]

    def do_init():
        init_result[0] = backup._ensure_initialized()
        init_done.set()

    t = threading.Thread(target=do_init)
    t.start()
    if init_done.wait(timeout=10.0):
        print(f"   Result: {init_result[0]}")
    else:
        print("   FAILED: Hung for >10s")
        sys.exit(1)

    print("\n6. Creating temp test file...")
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("Test content for OneDrive upload\n" * 100)
        test_file = Path(f.name)
    print(f"   File: {test_file} ({test_file.stat().st_size} bytes)")

    print("\n7. Testing sync upload (30s timeout)...")
    upload_done = threading.Event()
    upload_result = [None]

    def do_upload():
        upload_result[0] = backup.upload_backup_sync(test_file, timeout=30.0)
        upload_done.set()

    t = threading.Thread(target=do_upload)
    t.start()
    if upload_done.wait(timeout=35.0):
        print(f"   Result: {upload_result[0]}")
    else:
        print("   FAILED: Upload hung for >35s")
        sys.exit(1)

    print("\n8. Cleanup...")
    test_file.unlink()
    print("   Done")

    print("\n" + "=" * 70)
    print("All basic tests passed!")
    print("=" * 70)
