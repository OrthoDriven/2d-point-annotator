
import sys
from pathlib import Path
import asyncio
import json
import argparse
from tqdm import tqdm

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from auth import get_graph_client, SHAREPOINT_DRIVE_ID, BASE_BACKUP_FOLDER
from download_graph import _list_children, _download_folder_recursive

BACKUP_ROOT = PROJECT_ROOT / "data" / "remote_backups"

def load_study_data():
    with open(PROJECT_ROOT / "data" / "studies.json", "r") as f:
        studies = json.load(f)["studies"]
    with open(PROJECT_ROOT / "data" / "datasets.json", "r") as f:
        datasets = {d["id"]: d for d in json.load(f)["datasets"]}
    return studies, datasets

async def download_summary(client, dataset_config, summary_name):
    summary_path = BACKUP_ROOT / summary_name
    print(f"Downloading {summary_name}...")
    dataset_drive_id = dataset_config["drive_id"]
    
    try:
        items = await (
            client.drives.by_drive_id(dataset_drive_id)
            .items.by_drive_item_id(f"root:{dataset_config['folder_path']}:")
            .children.get()
        )
    except Exception as e:
        # Check if it's a 404/itemNotFound error (MS Graph APIError has nested error attribute)
        if hasattr(e, 'error') and hasattr(e.error, 'code') and e.error.code == 'itemNotFound':
            raise FileNotFoundError(f"Folder {dataset_config['folder_path']} not found in dataset drive.")
        elif hasattr(e, 'code') and getattr(e, 'code', None) == 'itemNotFound':
            raise FileNotFoundError(f"Folder {dataset_config['folder_path']} not found in dataset drive.")
        else:
            raise
    
    summary_item = next((item for item in items.value if item.name == summary_name), None)
    if not summary_item:
        raise FileNotFoundError(f"{summary_name} not found in {dataset_config['folder_path']}.")
        
    content = await (
        client.drives.by_drive_id(dataset_drive_id)
        .items.by_drive_item_id(summary_item.id)
        .content.get()
    )
    
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    with open(summary_path, "wb") as f:
        f.write(content)
    return summary_path

async def download_user_latest(client, username, dest_root):
    user_path = f"root:/{BASE_BACKUP_FOLDER}/{username}:"
    print(f"Listing backups for {username}...")
    try:
        backups = await _list_children(client, SHAREPOINT_DRIVE_ID, user_path)
    except Exception as e:
        # Check if it's a 404/itemNotFound error
        # The error shows as APIError with error.code='itemNotFound' (nested in error attribute)
        if hasattr(e, 'error') and hasattr(e.error, 'code') and e.error.code == 'itemNotFound':
            print(f"  No backup folder found for {username} (skipping)")
            return
        elif hasattr(e, 'code') and getattr(e, 'code', None) == 'itemNotFound':
            print(f"  No backup folder found for {username} (skipping)")
            return
        else:
            print(f"Error listing backups for {username}: {e}")
            return

    if not backups:
        print(f"  No backups found for {username}")
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
    if not json_file.exists():
        return 0, 0
    with open(json_file, 'r') as f:
        data = json.load(f)
    
    images = data.get("images", [])
    total_images = len(images)
    annotated_images = sum(1 for img in images if len(img.get("annotations", {})) > 0)
    
    return annotated_images, total_images

async def run_study_report(client, study, dataset_config, skip_missing=False):
    summary_name = f"{study['output_prefix']}_summary.json"
    summary_path = BACKUP_ROOT / summary_name
    
    if not summary_path.exists():
        summary_path = await download_summary(client, dataset_config, summary_name)
    
    with open(summary_path, "r") as f:
        summary_data = json.load(f)
    
    group_mapping = summary_data.get("group_mapping", {})
    final_group_sizes = summary_data.get("final_group_sizes", {})
    annotators_in_study = study["annotator_names"]
    
    dest_root = BACKUP_ROOT
    folder_mapping = {"scott": "SAB", "andrew": "ajj"}
    
    # Download files for all annotators in this study
    downloaded_users = []
    for annotator in annotators_in_study:
        user_folder = folder_mapping.get(annotator, annotator)
        await download_user_latest(client, user_folder, dest_root)
        downloaded_users.append(user_folder)
    
    if downloaded_users:
        print("\nDownload complete.\n")
    else:
        print("\nNo user backups downloaded.\n")

    with open(summary_path, "r") as f:
        summary_data = json.load(f)
    
    group_mapping = summary_data.get("group_mapping", {})
    final_group_sizes = summary_data.get("final_group_sizes", {})

    print(f"--- Study: {study['id']} ---")
    print(f"{'Annotator':<10} | {'Group':<10} | {'Progress':<10} | {'Images (Ann/Total)'}")
    print("-" * 70)

    total_annotated = 0
    total_expected = 0

    for group_id, group_info in group_mapping.items():
        annotator = group_info["annotator"]
        if annotator not in annotators_in_study:
            continue
        
        target_file = group_info["file"]
        user_folder = folder_mapping.get(annotator, annotator)
        file_path = dest_root / user_folder / target_file
        
        if user_folder == "ajj" and "andrew" not in target_file:
            continue
        
        annotated, _ = get_annotation_completion_stats(file_path)
        group_size = final_group_sizes.get(group_id, 0)
        
        if group_size > 0:
            percentage = (annotated / group_size) * 100
            print(f"{annotator:<10} | {group_id:<10} | {percentage:6.2f}% | {annotated}/{group_size}")
            total_annotated += annotated
            total_expected += group_size


    print("-" * 70)
    if total_expected > 0:
        percentage = (total_annotated / total_expected) * 100
        print(f"{'STUDY TOTAL':<10} | {'':<10} | {percentage:6.2f}% | {total_annotated}/{total_expected}")
    print()
    return total_annotated, total_expected

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--study", help="Study ID to report on")
    parser.add_argument("--skip-missing", action="store_true", 
                       help="Skip users with missing backup folders (quiet mode)")
    args = parser.parse_args()
    
    studies, datasets = load_study_data()
    client = get_graph_client()
    
    global_annotated = 0
    global_expected = 0
    
    if args.study:
        study = next((s for s in studies if s["id"] == args.study), None)
        if not study:
            print(f"Study {args.study} not found.")
            return
        await run_study_report(client, study, datasets[study["dataset_id"]], 
                              skip_missing=args.skip_missing)
    else:
        for study in studies:
            a, e = await run_study_report(client, study, datasets[study["dataset_id"]], 
                                         skip_missing=args.skip_missing)
            global_annotated += a
            global_expected += e
        
        if global_expected > 0:
            percentage = (global_annotated / global_expected) * 100
            print("-" * 70)
            print(f"{'GLOBAL':<10} | {'':<10} | {percentage:6.2f}% | {global_annotated}/{global_expected}")

if __name__ == "__main__":
    asyncio.run(main())
