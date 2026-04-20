#!/usr/bin/env python3

from pathlib import Path

REMOTE_BACKUP_PATH = Path("data/remote_backups/")


def get_files():
    print(REMOTE_BACKUP_PATH.exists())
    for root, dirs, files in REMOTE_BACKUP_PATH.walk():
        for file in files:
            files = (root / file).parents[1]
            print(files)


def main():
    get_files()


if __name__ == "__main__":
    main()
