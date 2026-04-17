
import json
from pathlib import Path

SUMMARY_LOCATION_FILE = Path("./data/remote_backups/summary_location.json")
SUMMARY_FILE_NAME = "fluoro-r1_summary.json"
REMOTE_FOLDER_PATH = "fluoro_images_round_1"

def save_summary_location(location):
    with open(SUMMARY_LOCATION_FILE, "w") as f:
        json.dump({"path": location}, f)

save_summary_location(REMOTE_FOLDER_PATH + "/" + SUMMARY_FILE_NAME)

with open(SUMMARY_FILE_NAME, "r") as f:
    summary_data = json.load(f)

print("Study Totals Summary (global_accounting):")
print(json.dumps(summary_data.get("global_accounting"), indent=2))

print("\nFinal Group Sizes:")
print(json.dumps(summary_data.get("final_group_sizes"), indent=2))
