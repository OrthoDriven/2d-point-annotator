
import sys
from pathlib import Path
import asyncio
PROJECT_ROOT = Path('.').resolve()
sys.path.insert(0, str(PROJECT_ROOT / 'src'))
from auth import get_graph_client, SHAREPOINT_DRIVE_ID
from download_graph import _list_children

async def find_file(client, drive_id, item_path, target_name):
    print(f"Checking {item_path}...")
    items = await _list_children(client, drive_id, item_path)
    for item in items:
        if item.name == target_name:
            print(f"Found {target_name} at {item_path}")
            return True
        if item.folder:
            if await find_file(client, drive_id, f'{item_path}/{item.name}', target_name):
                return True
    return False

async def main():
    client = get_graph_client()
    # List top level folders and search in each
    top_items = await _list_children(client, SHAREPOINT_DRIVE_ID, 'root')
    for item in top_items:
        if item.folder:
            await find_file(client, SHAREPOINT_DRIVE_ID, f'root:/{item.name}:', 'summary.json')

asyncio.run(main())
