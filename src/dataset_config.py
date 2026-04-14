import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional
import platform

from dirs import BASE_DIR


@dataclass
class DatasetEntry:
    id: str
    name: str
    subfolder: str
    description: Optional[str] = None
    zip_url: Optional[str] = None
    drive_id: Optional[str] = None
    folder_path: Optional[str] = None


@dataclass
class DatasetsConfig:
    download_method: str
    datasets: List[DatasetEntry] = field(default_factory=list)


def get_install_root() -> Path:
    system = platform.system()
    app_name_unix = "2d-point-annotator"
    app_name_windows = "2D-Point-Annotator"
    if system == "Windows":
        try:
            import platformdirs

            return Path(platformdirs.user_documents_dir()) / app_name_windows
        except ImportError:
            return Path.home() / app_name_windows
    return Path.home() / app_name_unix


def get_data_dir() -> Path:
    return get_install_root() / "data"


def get_dataset_dest(dataset: DatasetEntry) -> Path:
    return get_data_dir() / dataset.subfolder


def load_datasets_config(config_path: Optional[Path] = None) -> DatasetsConfig:
    if config_path is None:
        config_path = BASE_DIR / "data" / "datasets.json"

    if not config_path.exists():
        return DatasetsConfig(download_method="zip", datasets=[])

    with open(config_path, "r") as f:
        data = json.load(f)

    datasets = [DatasetEntry(**ds) for ds in data.get("datasets", [])]
    return DatasetsConfig(
        download_method=data.get("download_method", "zip"), datasets=datasets
    )
