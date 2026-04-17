
import sys
from pathlib import Path
import asyncio

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from auth import get_graph_client, SHAREPOINT_DRIVE_ID, BASE_BACKUP_FOLDER
from download_graph import _list_children, _download_folder_recursive

async def download_user_latest(client, username):
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
    print(f"Latest backup for {username} is {latest_backup.name}")
    
    dest = PROJECT_ROOT / "data" / "remote_backups" / username
    dest.mkdir(parents=True, exist_ok=True)
    
    print(f"Downloading to {dest}...")
    sem = asyncio.Semaphore(8)
    file_count = [0]
    
    await _download_folder_recursive(
        client,
        SHAREPOINT_DRIVE_ID,
        f"{BASE_BACKUP_FOLDER}/{username}/{latest_backup.name}",
        dest,
        print,
        file_count,
        sem
    )
    print(f"Downloaded {file_count[0]} files for {username}")

async def main():
    client = get_graph_client()
    users = ["ajj", "mark", "SAB"]
    for user in users:
        await download_user_latest(client, user)

if __name__ == "__main__":
    asyncio.run(main())
