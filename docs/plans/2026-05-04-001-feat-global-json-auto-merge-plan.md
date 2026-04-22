---
title: "feat: Global JSON Auto-Merge on Load"
type: feat
status: active
date: 2026-05-04
---

# Global JSON Auto-Merge on Load

## Overview

Replace the per-file, per-annotator `json_update_rules.json` system with a single global behavior: when a user loads any JSON, automatically check if a matching filename exists in the repo's `data/` directory. If the source version has a different image list, merge it — keeping all user annotations, adding new images from the source, and dropping unannotated images the source no longer contains.

This lets Andrew push updated JSONs to the repo (via commit + installer update) and have users automatically pick up new images without manual rules or user intervention.

---

## Problem Frame

**Current state:**
- `json_updater.py` implements a per-rule system (`data/json_update_rules.json`) that requires explicit configuration for each annotator/file pair
- Rules are brittle: if Andrew forgets to add a rule, users don't get updates
- The system is overcomplicated for the actual need: "push new images to users"

**What's needed:**
- A single global mechanism that works for any JSON file
- On load: compare the user's local JSON against the repo's source version
- If image lists differ: merge, preserving all existing annotations
- No per-file configuration — just works by filename matching

**Key invariant:** Never overwrite annotations a user has already made.

---

## Requirements Trace

- R1. When a user loads a JSON file, if a file with the same name exists in the repo `data/` directory, compare image lists automatically
- R2. If the source has images the local file doesn't: add them (as blank entries)
- R3. If the local file has images the source doesn't: keep them only if annotated; drop if unannotated
- R4. If annotated images exist locally: never overwrite their annotations, views, flags, or notes
- R5. Merge landmark/view definitions from the source (so protocol updates propagate)
- R6. Remove the per-file `json_update_rules.json` system (replaced by this global behavior)

---

## Scope Boundaries

- Does NOT change the annotation workflow itself
- Does NOT change how OneDrive backup works
- Does NOT add UI for managing merges — it's automatic and silent
- Does NOT handle the case where the user's filename doesn't match any repo file (no change to current behavior)

---

## Context & Research

### Relevant Code and Patterns

- `src/json_updater.py` — current rules engine (to be replaced/simplified)
- `src/main.py` lines ~920-960 — `load_data()` method where rules are checked and applied
- `src/json_updater.py` `_merge_image_lists()` — existing merge logic that already does the right thing
- `src/json_updater.py` `_get_annotated_images()` — existing annotation detection
- `data/*.json` — source JSON files in the repo
- `src/dataset_config.py` `get_data_dir()` — returns `~/2d-point-annotator/data/` (user's local data dir)
- `src/dirs.py` `BASE_DIR` — repo root for finding source `data/` directory

### Key Existing Patterns

- **Atomic JSON writes**: write to `.tmp` then `Path.replace()` (already in `_save_json_file()`)
- **Annotation detection**: check for non-null `value` in annotations, non-null `view`, or `image_flag=True`
- **Path-based image matching**: `image_path` field is the unique key per image record

---

## Key Technical Decisions

- **Filename matching, not hash comparison**: Match by filename (`fluoro-r2_round2_andrew.json`). If the repo has a file with the same name, treat it as the source of truth. Simple, predictable, no version tracking needed.
- **Source location**: Use the repo's `data/` directory (accessible via `BASE_DIR / "data"`). This is where Andrew commits updated JSONs. Users get them via installer updates or git pull.
- **Merge direction**: Source (repo) is authoritative for image list and landmark/view definitions. Local is authoritative for annotations. This means: if Andrew removes an image from the source, unannotated copies are dropped; annotated copies are kept.
- **Silent merge with logging**: No user-facing dialog. Merge happens automatically on load. Results logged to `annotator.log` for debugging.
- **Replace, don't layer**: Remove the `json_update_rules.json` system entirely. The global merge makes it redundant.

---

## Open Questions

### Resolved During Planning

- **Q: What if the user renames their JSON?** A: No match → no merge. User's choice.
- **Q: What if the source has different landmarks/views?** A: Source wins for landmarks/views (protocol updates propagate). Annotations are keyed by landmark name, so if a landmark is removed from the source, existing annotations for it become orphaned but harmless.
- **Q: Should this run on every load or only when source is newer?** A: Every load. The merge is idempotent — if nothing changed, it's a no-op. Checking mtimes adds complexity for no benefit.

### Deferred to Implementation

- Exact method name and module placement for the new merge function
- Whether to keep `json_updater.py` as a thin wrapper or delete entirely

---

## Implementation Units

- [ ] U1. **Create `src/auto_merge.py` with global merge logic**

**Goal:** Extract and simplify the merge logic from `json_updater.py` into a standalone module that works for any JSON by filename matching.

**Requirements:** R1, R2, R3, R4, R5

**Dependencies:** None

**Files:**
- Create: `src/auto_merge.py`
- Reference: `src/json_updater.py` (existing merge logic to adapt)

**Approach:**
- New function `auto_merge_on_load(local_json_path: Path) -> dict`:
  1. Extract filename from `local_json_path`
  2. Check if `BASE_DIR / "data" / filename` exists
  3. If no source found: return original data unchanged
  4. Load both local and source JSON
  5. Call `_merge_image_lists()` (reuse from `json_updater.py` or reimplement)
  6. Update landmarks/views from source
  7. If any changes were made: write merged result back to `local_json_path` atomically
  8. Return the merged data dict
- Reuse `_get_annotated_images()` logic for annotation detection
- Log merge stats (images kept/added/removed) to logger

**Patterns to follow:**
- `json_updater.py` `_merge_image_lists()` — keep annotated, add new, drop unannotated old
- `json_updater.py` `_get_annotated_images()` — annotation detection heuristic
- `json_updater.py` `apply_rule()` — atomic write pattern (`.tmp` then `replace`)

**Test scenarios:**
- Happy path: Local has 5 images (3 annotated), source has 7 images (5 overlap) → result has 7 images, 3 annotated ones preserved
- Happy path: Source has no new images → no changes, local file unchanged
- Edge case: Source file doesn't exist → local loaded as-is, no error
- Edge case: Local has annotated image removed from source → annotated image kept
- Edge case: Local has unannotated image removed from source → image dropped
- Error path: Source JSON is malformed → local loaded as-is, warning logged
- Integration: Load a JSON through `auto_merge_on_load()`, save, reload → same result (idempotent)

**Verification:**
- Create a test local JSON with 3 annotated images
- Create a source JSON with 2 of those + 1 new image
- Run `auto_merge_on_load()` → verify result has all 4 images, annotations preserved

---

- [ ] U2. **Integrate auto-merge into `load_data()` in main.py**

**Goal:** Wire the auto-merge into the existing data loading flow so it runs transparently when any JSON is loaded.

**Requirements:** R1, R4

**Dependencies:** U1

**Files:**
- Modify: `src/main.py` (in `load_data()`, replace `json_updater` call with `auto_merge`)

**Approach:**
- In `load_data()`, after the file is read and validated, call `auto_merge_on_load(json_path)`
- Use the returned data dict (which may be merged) for the rest of the method
- Remove the existing `from json_updater import check_and_apply_rules` block
- Add a status message or log entry when a merge occurs

**Patterns to follow:**
- Existing `load_data()` flow: read JSON → validate → process images
- The `json_updater` integration block (lines ~920-960) that this replaces

**Test scenarios:**
- Happy path: Load a JSON that has a matching source → images merged, annotations preserved
- Happy path: Load a JSON with no matching source → loads normally, no merge
- Integration: Load, annotate, save, reload → annotations persist through merge cycle

**Verification:**
- Load a JSON file, verify merge happens (check log or returned data)
- Load a non-matching JSON, verify no merge attempted

---

- [ ] U3. **Remove `json_update_rules.json` system**

**Goal:** Clean up the old per-file rules system that is now replaced by the global auto-merge.

**Requirements:** R6

**Dependencies:** U2 (auto-merge must be working first)

**Files:**
- Delete: `data/json_update_rules.json`
- Delete or gut: `src/json_updater.py`
- Remove: `.update_tracking/` directory reference if any
- Modify: `src/main.py` (remove any remaining references to `json_updater`)

**Approach:**
- Delete the rules JSON file
- Either delete `json_updater.py` entirely or reduce it to a stub that logs a deprecation warning
- Remove the tracking directory (`.update_tracking/`) if it exists
- Clean up any imports or references in `main.py`

**Test scenarios:**
- Happy path: App starts without errors after removal
- Happy path: Loading a JSON works normally (auto-merge handles it)

**Verification:**
- `grep -r json_updater src/` returns no hits
- App launches and loads JSONs normally

---

## System-Wide Impact

- **Interaction graph**: `load_data()` calls `auto_merge_on_load()` before processing images. No other entry points affected.
- **Error propagation**: Merge failures are logged but never block loading — the local JSON is always usable as-is.
- **State lifecycle risks**: None — merge writes to disk before `load_data()` reads the result, so in-memory state is always consistent.
- **API surface parity**: JSON format unchanged. No new fields required.
- **Unchanged invariants**: OneDrive backup, autosave, annotation workflow — all untouched.

---

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| Source JSON has corrupted landmark definitions | Merge only updates landmarks/views if source loads successfully |
| User accidentally edits source JSON in repo | Source is version-controlled; easy to revert |
| Merge overwrites user's intentional edits to image metadata | Only annotations/views/flags are protected; other metadata (like `image_direction`) comes from source — document this behavior |

---

## Documentation / Operational Notes

- Update `AGENTS.md` to note the auto-merge behavior
- No installer changes needed — source `data/` directory is already part of the repo
- Andrew's workflow: edit JSON in repo → commit → push → users get updates on next app load
