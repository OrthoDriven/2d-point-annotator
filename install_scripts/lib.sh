#!/usr/bin/env bash
set -euo pipefail

# -----------------------------
# Small helpers
# -----------------------------
die() {
    echo "[error] $*" >&2
    exit 1
}
log() { echo "$*"; }

script_dir() {
    cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd
}

require_file() {
    [[ -f "$1" ]] || die "Missing required file: $1"
}

require_dir() {
    [[ -d "$1" ]] || die "Missing required directory: $1"
}

utc_now_iso() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }

utc_to_epoch() {
    # GNU date (Fedora) compatible
    date -u -d "$1" +%s 2>/dev/null || echo "0"
}

# -----------------------------
# Load env (installer-written)
# -----------------------------
load_app_env() {
    local default_env="$HOME/2d-point-annotator/app.env"
    local env_file="${APP_ENV_FILE:-$default_env}"

    [[ -f "$env_file" ]] || die "Missing app env file: $env_file"

    # shellcheck source=/dev/null
    source "$env_file"

    # Required variables (installer-written)
    : "${INSTALL_ROOT:?INSTALL_ROOT missing in app.env}"
    : "${APP_DIR:?APP_DIR missing in app.env}"
    : "${REPO_ZIP_URL:?REPO_ZIP_URL missing in app.env}"
    : "${API_URL:?API_URL missing in app.env}"

    # Optional defaults
    : "${USER_AGENT:=2d-point-annotator-updater}"
    : "${REQUEST_TIMEOUT_SEC:=15}"
    : "${MIN_CHECK_INTERVAL_SECONDS:=15}"
}

# -----------------------------
# GitHub check + download
# -----------------------------
github_latest_sha_etag() {
    # Outputs: "http_code|sha|etag"
    local state_etag="${1:-}"

    local tmp_dir="${2:?tmp_dir required}"
    mkdir -p "$tmp_dir"
    local hdr_file="$tmp_dir/headers.txt"
    local body_file="$tmp_dir/body.json"

    local -a headers
    headers=(-H "User-Agent: ${USER_AGENT}")
    if [[ -n "${state_etag}" ]]; then
        headers+=(-H "If-None-Match: ${state_etag}")
    fi

    local http_code
    http_code="$(
        curl -sS -L \
            --connect-timeout "${REQUEST_TIMEOUT_SEC}" \
            --max-time "${REQUEST_TIMEOUT_SEC}" \
            -D "$hdr_file" \
            -o "$body_file" \
            -w "%{http_code}" \
            "${headers[@]}" \
            "$API_URL" ||
            true
    )"

    local new_etag=""
    new_etag="$(grep -i '^etag:' "$hdr_file" | head -n1 | sed -E 's/^etag:[[:space:]]*//I' | tr -d '\r' || true)"

    local new_sha=""
    if [[ "$http_code" == "200" ]]; then
        new_sha="$(
            pixi run python - "$body_file" <<'PY'
import json, sys
path = sys.argv[1]
with open(path, "r", encoding="utf-8") as f:
    obj = json.load(f)
print(obj.get("sha",""))
PY
        )"
    fi

    printf "%s|%s|%s" "$http_code" "$new_sha" "$new_etag"
}

download_repo_zip() {
    # download_repo_zip <zip_url> <out_zip_path>
    local zip_url="${1:?zip_url required}"
    local out_zip="${2:?out_zip required}"

    curl -sS -L \
        --connect-timeout "${REQUEST_TIMEOUT_SEC}" \
        --max-time "$((REQUEST_TIMEOUT_SEC * 6))" \
        -H "User-Agent: ${USER_AGENT}" \
        -o "$out_zip" \
        "$zip_url"
}

extract_zip() {
    # extract_zip <zip_path> <dest_dir>
    local zip_path="${1:?zip_path required}"
    local dest_dir="${2:?dest_dir required}"
    unzip -oq "$zip_path" -d "$dest_dir"
}

find_project_root_containing_pixi() {
    # find_project_root_containing_pixi <search_root>
    local root="${1:?search_root required}"
    find "$root" -type f -name pixi.toml -print0 -quit | xargs -0 dirname
}

# -----------------------------
# Atomic-ish swap
# -----------------------------
swap_app_dir() {
    # swap_app_dir <new_project_dir>
    local new_project_dir="${1:?new_project_dir required}"

    local new_path="$INSTALL_ROOT/app.new"
    local old_path="$INSTALL_ROOT/app.old"

    rm -rf "$new_path"
    mkdir -p "$INSTALL_ROOT"
    mv "$new_project_dir" "$new_path"

    rollback() {
        log "[error] Swap failed; attempting rollback..."
        if [[ ! -d "$APP_DIR" && -d "$old_path" ]]; then
            mv "$old_path" "$APP_DIR" || true
        fi
        rm -rf "$new_path" || true
    }
    trap rollback ERR

    if [[ -d "$APP_DIR" ]]; then
        rm -rf "$old_path"
        mv "$APP_DIR" "$old_path"
    fi

    mv "$new_path" "$APP_DIR"
    rm -rf "$old_path"
    trap - ERR
}

# -----------------------------
# State JSON (python3)
# -----------------------------
state_init_if_missing() {
    # state_init_if_missing <state_path>
    local state_path="${1:?state_path required}"
    if [[ ! -f "$state_path" ]]; then
        local now
        now="$(utc_now_iso)"
        pixi run python - "$state_path" "$now" <<'PY'
import json, sys
path, now = sys.argv[1], sys.argv[2]
obj = {"sha":"", "etag":"", "updatedUtc": now, "lastCheckUtc": "1970-01-01T00:00:00Z"}
with open(path, "w", encoding="utf-8") as f:
    json.dump(obj, f, indent=2)
PY
    fi
}

state_get() {
    # state_get <state_path> <key> <default>
    pixi run python - "$1" "$2" "$3" <<'PY'
import json, sys
path, key, default = sys.argv[1], sys.argv[2], sys.argv[3]
try:
    with open(path, "r", encoding="utf-8") as f:
        obj = json.load(f)
    v = obj.get(key, default)
    print(default if v is None else v)
except Exception:
    print(default)
PY
}

state_touch_lastcheck() {
    # state_touch_lastcheck <state_path>
    local state_path="${1:?state_path required}"
    local now
    now="$(utc_now_iso)"
    pixi run python - "$state_path" "$now" <<'PY'
import json, sys
path, now = sys.argv[1], sys.argv[2]
try:
    with open(path, "r", encoding="utf-8") as f:
        obj = json.load(f)
except Exception:
    obj = {}
obj["lastCheckUtc"] = now
with open(path, "w", encoding="utf-8") as f:
    json.dump(obj, f, indent=2)
PY
}

state_set_all() {
    # state_set_all <state_path> <sha> <etag>
    local state_path="${1:?state_path required}"
    local sha="${2:?sha required}"
    local etag="${3:-}"
    local now
    now="$(utc_now_iso)"
    pixi run python - "$state_path" "$sha" "$etag" "$now" <<'PY'
import json, sys
path, sha, etag, now = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
obj = {"sha":sha, "etag":etag, "updatedUtc": now, "lastCheckUtc": now}
with open(path, "w", encoding="utf-8") as f:
    json.dump(obj, f, indent=2)
PY
}
