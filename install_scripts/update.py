#!/usr/bin/env python3
"""Branch-aware updater for 2D Point Annotator."""

import json
import os
import shutil
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import requests

DEFAULT_INSTALL_ROOT = Path.home() / "2d-point-annotator"
DEFAULT_ENV_PATH = DEFAULT_INSTALL_ROOT / "app.env"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def load_env_file(env_path: Path) -> dict:
    data = {}
    if not env_path.exists():
        return data
    for line in env_path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        data[key.strip()] = value
    return data


def load_config() -> dict:
    env_path = Path(os.environ.get('APP_ENV_FILE', DEFAULT_ENV_PATH))
    env = load_env_file(env_path)
    install_root = Path(env.get('INSTALL_ROOT', str(DEFAULT_INSTALL_ROOT)))
    app_dir = Path(env.get('APP_DIR', str(install_root / 'app')))
    return {
        'ENV_PATH': env_path,
        'INSTALL_ROOT': install_root,
        'APP_DIR': app_dir,
        'STATE_PATH': Path(env.get('STATE_PATH', str(install_root / 'update_state.json'))),
        'USER_AGENT': env.get('USER_AGENT', '2d-point-annotator-updater'),
        'MIN_CHECK_INTERVAL_SECONDS': int(env.get('MIN_CHECK_INTERVAL_SECONDS', '15')),
        'REQUEST_TIMEOUT_SEC': int(env.get('REQUEST_TIMEOUT_SEC', '15')),
        'API_URL': env.get('API_URL', 'https://api.github.com/repos/OrthoDriven/2d-point-annotator/commits/new-prototype'),
        'REPO_ZIP_URL': env.get('REPO_ZIP_URL', 'https://github.com/OrthoDriven/2d-point-annotator/archive/refs/heads/new-prototype.zip'),
    }


def load_state(state_path: Path) -> dict:
    if not state_path.exists():
        return {'sha': '', 'etag': '', 'updatedUtc': utc_now(), 'lastCheckUtc': '1970-01-01T00:00:00Z'}
    try:
        return json.loads(state_path.read_text(encoding='utf-8'))
    except Exception:
        return {'sha': '', 'etag': '', 'updatedUtc': utc_now(), 'lastCheckUtc': '1970-01-01T00:00:00Z'}


def save_state(state_path: Path, state: dict) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, indent=2), encoding='utf-8')


def should_check_for_updates(state: dict, min_interval: int):
    try:
        last_check = datetime.fromisoformat(state.get('lastCheckUtc', '1970-01-01T00:00:00+00:00').replace('Z', '+00:00'))
    except Exception:
        return True
    delta = (datetime.now(timezone.utc) - last_check).total_seconds()
    if delta < 0:
        return True
    return delta >= min_interval


def check_for_updates(config: dict, state: dict) -> dict:
    headers = {'User-Agent': config['USER_AGENT']}
    if state.get('etag'):
        headers['If-None-Match'] = state['etag']
    response = requests.get(config['API_URL'], headers=headers, timeout=config['REQUEST_TIMEOUT_SEC'])
    if response.status_code == 304:
        return {'status': 'unchanged', 'etag': state.get('etag', ''), 'sha': state.get('sha', '')}
    response.raise_for_status()
    data = response.json()
    if isinstance(data, list):
        data = data[0] if data else {}
    return {
        'status': 'new',
        'sha': data.get('sha', ''),
        'etag': response.headers.get('ETag', ''),
    }


def download_repo_zip(zip_url: str, download_path: Path, timeout: int) -> None:
    with requests.get(zip_url, stream=True, timeout=timeout) as response:
        response.raise_for_status()
        with open(download_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)


def find_project_root(extract_dir: Path):
    for path in extract_dir.rglob('pixi.toml'):
        return path.parent
    return None


def atomic_swap(new_dir: Path, app_dir: Path) -> None:
    app_dir = Path(app_dir)
    install_root = app_dir.parent
    new_path = install_root / 'app.new'
    old_path = install_root / 'app.old'
    if new_path.exists():
        shutil.rmtree(new_path, ignore_errors=True)
    if old_path.exists():
        shutil.rmtree(old_path, ignore_errors=True)
    shutil.move(str(new_dir), str(new_path))
    try:
        if app_dir.exists():
            app_dir.rename(old_path)
        new_path.rename(app_dir)
        if old_path.exists():
            shutil.rmtree(old_path, ignore_errors=True)
    except Exception:
        if not app_dir.exists() and old_path.exists():
            old_path.rename(app_dir)
        if new_path.exists():
            shutil.rmtree(new_path, ignore_errors=True)
        raise


def run_update() -> None:
    config = load_config()
    state = load_state(config['STATE_PATH'])
    if not should_check_for_updates(state, config['MIN_CHECK_INTERVAL_SECONDS']):
        return

    state['lastCheckUtc'] = utc_now()
    save_state(config['STATE_PATH'], state)

    try:
        result = check_for_updates(config, state)
    except Exception as exc:
        print(f'[warn] Update check failed: {exc}')
        return

    if result['status'] == 'unchanged':
        return

    new_sha = result.get('sha', '')
    if not new_sha:
        print('[warn] GitHub response did not include a commit sha')
        return
    if state.get('sha') == new_sha:
        state['etag'] = result.get('etag', state.get('etag', ''))
        save_state(config['STATE_PATH'], state)
        return

    print(f'[info] New version detected ({new_sha}). Updating...')

    with tempfile.TemporaryDirectory() as temp_dir_str:
        temp_dir = Path(temp_dir_str)
        zip_path = temp_dir / 'annotator.zip'
        download_repo_zip(config['REPO_ZIP_URL'], zip_path, config['REQUEST_TIMEOUT_SEC'] * 6)
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(temp_dir)
        project_root = find_project_root(temp_dir)
        if not project_root:
            print('[error] Cannot find project root in downloaded archive')
            return
        atomic_swap(project_root, config['APP_DIR'])

    state['sha'] = new_sha
    state['etag'] = result.get('etag', state.get('etag', ''))
    state['updatedUtc'] = utc_now()
    save_state(config['STATE_PATH'], state)
    print(f'[info] Update complete -> {new_sha}')


if __name__ == '__main__':
    try:
        run_update()
    except KeyboardInterrupt:
        print('\n[info] Update cancelled by user')
        sys.exit(1)
    except Exception as exc:
        print(f'[error] {exc}')
        sys.exit(1)
