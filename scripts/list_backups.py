
import sys
from pathlib import Path
import asyncio

# Setup path to import src
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from auth import get_graph_client, SHAREPOINT_DRIVE_ID, BASE_BACKUP_FOLDER

async def list_backups():
    client = get_graph_client()
    
    drive_item_path = f"root:/{BASE_BACKUP_FOLDER}:"
    
    items = await (
        client.drives.by_drive_id(SHAREPOINT_DRIVE_ID)
        .items.by_drive_item_id(drive_item_path)
        .children.get()
    )
    
    print(f"Contents of {BASE_BACKUP_FOLDER}:")
    for item in items.value:
        print(f"- {item.name} (ID: {item.id})")

if __name__ == "__main__":
    asyncio.run(list_backups())
