import threading
from typing import Callable, Optional

from dataset_config import DatasetEntry, get_dataset_dest


def download_dataset(
    dataset: DatasetEntry,
    method: str,
    on_progress: Optional[Callable[[str], None]] = None,
    on_done: Optional[Callable[[Optional[Exception]], None]] = None,
    skip_existing: bool = False,
) -> threading.Thread:
    """
    Download a dataset using the specified method in a background thread.

    Parameters
    ----------
    dataset : DatasetEntry
        The dataset to download.
    method : str
        "zip" or "graph".
    on_progress : callable, optional
        Called from the background thread with a status string.
    on_done : callable, optional
        Called when finished with None (success) or the Exception.
    """

    def _run() -> None:
        exc: Optional[Exception] = None
        try:
            dest = get_dataset_dest(dataset)

            if method == "zip":
                from download_zip import download_zip

                if not dataset.zip_url:
                    raise ValueError(
                        f"Dataset '{dataset.name}' has no zip_url configured"
                    )
                download_zip(
                    dataset.zip_url, dest, on_progress, skip_existing
                )
            elif method == "graph":
                from download_graph import download_graph

                if not dataset.drive_id or not dataset.folder_path:
                    raise ValueError(
                        f"Dataset '{dataset.name}' missing drive_id or folder_path"
                    )
                download_graph(
                    dataset.drive_id,
                    dataset.folder_path,
                    dest,
                    on_progress,
                    skip_existing,
                )
            else:
                raise ValueError(f"Unknown download method: {method}")
        except Exception as e:
            exc = e
            if on_progress:
                on_progress(f"Error: {e}")
        finally:
            if on_done:
                on_done(exc)

    t = threading.Thread(target=_run, name=f"dl-{dataset.id}", daemon=True)
    t.start()
    return t
