
import sys
from pathlib import Path
import asyncio
import json
from tqdm import tqdm

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from auth import get_graph_client, SHAREPOINT_DRIVE_ID, BASE_BACKUP_FOLDER
from download_graph import _list_children, _download_folder_recursive

async def download_user_latest(client, username, dest_root):
    user_path = f"root:/{BASE_BACKUP_FOLDER}/{username}:"
    print(f"Listing backups for {username}...")
    try:
        backups = await _list_children(client, SHAREPOINT_DRIVE_ID, user_path)
    except Exception as e:
        print(f"Error listing backups for {username}: {e}")
        return

    if not backups:
        print(f"No backups found for {username}")
        return

    backups.sort(key=lambda x: x.name, reverse=True)
    latest_backup = backups[0]
    
    dest = dest_root / username
    dest.mkdir(parents=True, exist_ok=True)
    
    sem = asyncio.Semaphore(8)
    file_count = [0]
    
    pbar = tqdm(desc=f"Downloading {username}", unit="file")
    
    def progress_wrapper(msg):
        if "Downloading file" in msg:
            pbar.update(1)

    await _download_folder_recursive(
        client,
        SHAREPOINT_DRIVE_ID,
        f"{BASE_BACKUP_FOLDER}/{username}/{latest_backup.name}",
        dest,
        progress_wrapper,
        file_count,
        sem
    )
    pbar.close()

def get_annotation_completion_stats(json_file):
    with open(json_file, 'r') as f:
        data = json.load(f)
    
    images = data.get("images", [])
    total_images = len(images)
    annotated_images = sum(1 for img in images if len(img.get("annotations", {})) > 0)
    
    return annotated_images, total_images

async def run_report():
    client = get_graph_client()
    users = ["ajj", "mark", "SAB"]
    dest_root = PROJECT_ROOT / "data" / "remote_backups"
    
    for user in users:
        await download_user_latest(client, user, dest_root)
    print("\nDownload complete.\n")

    with open("fluoro-r1_summary.json", "r") as f:
        summary_data = json.load(f)
    
    group_mapping = summary_data.get("group_mapping", {})
    final_group_sizes = summary_data.get("final_group_sizes", {})

    print(f"{'Annotator':<10} | {'Group':<10} | {'Progress':<10} | {'Images (Ann/Total)'}")
    print("-" * 70)

    total_annotated_global = 0
    total_expected_global = 0

    for user_dir in dest_root.iterdir():
        if user_dir.is_dir():
            for json_file in user_dir.glob("*.json"):
                if user_dir.name == "ajj" and "andrew" not in json_file.name:
                    continue

                annotated, _ = get_annotation_completion_stats(json_file)
                
                group_name = "Unknown"
                group_size = 0
                for g_id, g_info in group_mapping.items():
                    if g_info["file"] == json_file.name:
                        group_name = g_id
                        group_size = final_group_sizes.get(g_id, 0)
                        break
                
                if group_size > 0:
                    percentage = (annotated / group_size) * 100
                    print(f"{user_dir.name:<10} | {group_name:<10} | {percentage:6.2f}% | {annotated}/{group_size}")
                    total_annotated_global += annotated
                    total_expected_global += group_size

    print("-" * 70)
    if total_expected_global > 0:
        global_percentage = (total_annotated_global / total_expected_global) * 100
        print(f"{'GLOBAL':<10} | {'':<10} | {global_percentage:6.2f}% | {total_annotated_global}/{total_expected_global}")

if __name__ == "__main__":
    asyncio.run(run_report())


