#!/usr/bin/env python3
import sqlite3
from pathlib import Path, PurePath
from typing import Union


def init_db(db_path: Union[Path, str]) -> None:
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        create_table_query = """
        CREATE TABLE IF NOT EXISTS annotations (
            image_filename TEXT PRIMARY KEY,
            image_path TEXT,
            image_quality INTEGER DEFAULT 0,
            data TEXT, -- JSON blob of landmark data
            modified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """

        create_index_query = """
        CREATE INDEX IF NOT EXISTS idx_modified
        ON annotations(modified_at DESC)
        """
        cursor.execute(create_table_query)
        cursor.execute(create_index_query)
        conn.commit()
    return


def db_is_populated(db_path: Union[Path, str]) -> bool:
    is_populated = False
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        is_populated_query = """
        SELECT COUNT(*) FROM annotations
        """
        cursor.execute(is_populated_query)
        count = cursor.fetchone()[0]
        is_populated = count > 0

    return is_populated


def execute_single_db_query(db_path: Union[Path, str], query: str) -> None:
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(query)
        conn.commit()
    return


print(db_is_populated("./andrew_data/Landmark2DPointsLAT_testing_queue.db"))
