---
title: "feat: Admin Image Injection into JSON + OneDrive Backup of Originals"
type: feat
status: active
date: 2026-04-24
---

# Admin Image Injection into JSON + OneDrive Backup of Originals

## Overview

This plan adds two features for the admin (Andrew) workflow:

1. **Image injection into existing JSONs** — add new images to an existing annotation JSON without manually editing the file
2. **OneDrive backup of original JSONs** — before overwriting a JSON that was previously uploaded, back up the original to OneDrive for traceability

The end-user workflow (annotators downloading and annotating) stays unchanged. This is about making it easier to **create and maintain** the JSON files that annotators consume.

---

## Problem Frame

**Current admin workflow:**
1. Andrew creates JSON files locally with image lists
2. Manually uploads JSONs to OneDrive
3. Annotators download JSONs from OneDrive
4. Later, Andrew needs to add more images to an existing JSON (new images arrive, images were missed, etc.)
5. Currently: must manually edit the JSON or regenerate it from scratch

**Pain points:**
- No way to add images to an existing JSON from the GUI — must hand-edit or regenerate
- When a JSON is downloaded, modified, and re-uploaded, the original version is lost — no traceability
- No metadata tracking on when images were added or by whom

---

## Requirements Trace

- R1. Admin can add images to an existing JSON via file dialog or directory scan (from within the annotator GUI)
  - No, I will create the json and put them into some directory on the local machine. Because the installer will create a local copy of the repo, this new version of the file should be accessable by the end user. Then, there's essentially a gate that says, "did user X pick file Y, if so, edit the image list while keeping the existing annotations the same"

- R2. When a JSON is loaded and modified, the original version is backed up to OneDrive before overwrite
  - Yes that's correct
- R3. JSON metadata tracks when images were added (timestamp, count)
  - Yes that's correct

---

## Scope Boundaries

- End users (annotators) do NOT get image management features — they download and annotate
- Does NOT add image removal — admin regenerates if removal is needed
- Does NOT add quick-switch or fancy data picker — users already know their round/name
- Does NOT change the annotation workflow itself

---

## Context & Research

### Relevant Code and Patterns

- `src/main.py` — `AnnotationGUI` class, `load_data()` method (lines ~1190-1320), `_save_json_file()` (lines ~380-420), `_schedule_onedrive_backup()` (lines ~1850-1870)
- `src/auth.py` — `OneDriveBackup.upload_backup_sync()` for file uploads, `BASE_BACKUP_FOLDER = "pelvic-2d-points-backup"`
- `data/*.json` — annotation data files with `{landmarks, views, images[]}` schema
- `.memory-bank/architecture/onedrive-backup.md` — debounce, in-flight guard, SelectorEventLoop patterns

### Key Patterns to Follow

- **Atomic JSON writes**: write to `.tmp` then `Path.replace()` (existing `_save_json_file()`)
- **Debounced OneDrive backup**: `_schedule_onedrive_backup()` with 5s delay
- **Thread-safe uploads**: `upload_backup_sync()` creates fresh client per thread

---

## Key Technical Decisions

- **Backup-on-first-write**: Only back up the original JSON to OneDrive on the first save after loading, not on every save
- **Metadata tracking**: Add optional `metadata` top-level key to JSON with `created`, `last_modified`, `images_added_count`, `change_log[]`. Backward-compatible — older versions ignore unknown keys
- **Injection UI**: Add "Add Images" and "Add Directory" buttons in the right control panel, below the image Treeview

---

## Implementation Units

- [ ] U1. **Add `metadata` field to JSON format**

**Goal:** Add optional metadata tracking to the JSON schema for traceability.

**Requirements:** R3

**Dependencies:** None

**Files:**
- Modify: `src/main.py` (load_data, _save_json_file methods)

**Approach:**
- Add optional `metadata` top-level key with `created`, `last_modified`, `change_log[]`
- On first save of a JSON, populate `created` with ISO timestamp
- On every save, update `last_modified`
- `change_log` entries: `{timestamp, action, details}` where action is `images_added` with count
- Backward-compatible: readers ignore unknown top-level keys (same as `app_version`/`protocol_version`)

**Patterns to follow:**
- Existing `app_version` and `protocol_version` fields (written but not required for reading)

**Test scenarios:**
- Happy path: Load JSON without metadata, save adds metadata with created/last_modified
- Happy path: Add images to JSON, change_log records `images_added` with count
- Edge case: Load JSON with existing metadata, save preserves original `created` timestamp

**Verification:**
- Save a JSON, inspect it for `metadata` field with correct timestamps
- Add images, verify change_log entries appear

---

- [ ] U2. **OneDrive backup of original JSON before first modification**

**Goal:** Back up the original JSON to OneDrive before the first save that modifies it.

**Requirements:** R2

**Dependencies:** U1 (metadata tracking)

**Files:**
- Modify: `src/main.py` (load_data, _save_json_file methods)

**Approach:**
- On `load_data()`, record the JSON's content hash (SHA-256)
- On first `_save_json_file()` where content has changed, upload original to OneDrive
- Upload path: `pelvic-2d-points-backup/original_jsons/{username}/{filename}_{timestamp}.json`
- Use existing `OneDriveBackup.upload_backup_sync()` in a background thread
- Add `_original_json_hash` and `_original_json_backed_up` instance variables
- Reset on new JSON load

**Patterns to follow:**
- `_schedule_onedrive_backup()` with debounced timer
- `_backup_to_onedrive()` for background upload

**Test scenarios:**
- Happy path: Load JSON, add images, save → original uploaded to OneDrive
- Happy path: Load JSON, save without changes → no upload (hash unchanged)
- Edge case: OneDrive unavailable → save proceeds normally, backup skipped with warning

**Verification:**
- Load a JSON, make a change, save
- Check OneDrive at `original_jsons/{username}/` for backup file

---

- [ ] U3. **Image injection UI (Add Images / Add Directory)**

**Goal:** Allow the admin to add images to the current JSON from within the GUI.

**Requirements:** R1

**Dependencies:** U1 (metadata for change tracking)

**Files:**
- Modify: `src/main.py` (add UI buttons, implement add logic)

**Approach:**
- Add "Add Images" button below image Treeview → opens file dialog for image files
- Add "Add Directory" button → scans directory for images matching `possible_image_suffix`
- Resolve paths relative to JSON dir, check for duplicates, append to `json_data["images"]`
- After add: rebuild image Treeview, update metadata change_log, auto-save
- Confirm dialog for large batch adds (>50 images)

**Patterns to follow:**
- `possible_image_suffix` for image file filtering
- `_refresh_image_listbox()` for Treeview rebuild
- `_resolve_image_path()` for path resolution

**Test scenarios:**
- Happy path: Click "Add Images", select 3 TIF files → images appear in Treeview
- Happy path: Click "Add Directory", select folder → all images added
- Edge case: Add image that's already in list → skip with warning
- Edge case: Add directory with 0 images → warning message

**Verification:**
- Add 3 images to a JSON, save, reload → images persist
- Check metadata change_log for `images_added` entries

---

## System-Wide Impact

- **Interaction graph**: New UI buttons in right control panel, new methods on `AnnotationGUI`
- **Error propagation**: OneDrive backup failures are logged but don't block save
- **State lifecycle risks**: `_original_json_backed_up` flag must reset on new JSON load
- **API surface parity**: JSON format gains optional `metadata` field (backward-compatible)

---

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| OneDrive backup fails silently | Log warning, proceed with save (data is safe locally) |
| Large JSON files slow to hash | SHA-256 on ~100KB JSON is negligible (<1ms) |
| User adds 1000+ images accidentally | Confirm dialog for large batch adds (>50 images) |

---

## Documentation / Operational Notes

- Update `data-formats.md` memory bank doc with `metadata` field description
- No installer changes needed
