import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dataset_config import (  # noqa: E402
    DatasetEntry,
    DatasetsConfig,
    get_data_dir,
    get_dataset_dest,
    get_install_root,
    load_datasets_config,
)


def test_load_datasets_config(tmp_path):
    config_content = '{"download_method": "zip", "datasets": [{"id": "test-ds", "name": "Test Dataset", "subfolder": "test_folder"}]}'
    config_file = tmp_path / "datasets.json"
    config_file.write_text(config_content)

    config = load_datasets_config(config_file)
    assert config.download_method == "zip"
    assert len(config.datasets) == 1
    assert config.datasets[0].id == "test-ds"
    assert config.datasets[0].name == "Test Dataset"
    assert config.datasets[0].subfolder == "test_folder"


def test_load_missing_config(tmp_path):
    config = load_datasets_config(tmp_path / "nonexistent.json")
    assert config.download_method == "zip"
    assert config.datasets == []


def test_get_dataset_dest():
    ds = DatasetEntry(id="test", name="Test", subfolder="my_folder")
    dest = get_dataset_dest(ds)
    assert dest.name == "my_folder"
    assert dest.parent == get_data_dir()
