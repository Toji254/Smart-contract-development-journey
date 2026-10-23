#!/usr/bin/env bash
# ==============================================================================
# MarkTrail — Database Restore Script
# Safely restores a MarkTrail database backup after verifying integrity.
# Uses Python's built-in sqlite3 engine (no external sqlite3 CLI required).
# ==============================================================================
set -euo pipefail

usage() {
    echo "Usage: $0 <path-to-backup-file> [--force]"
    echo ""
    echo "Examples:"
    echo "  $0 /opt/marktrail/backups/marktrail_backup_20261023_120000Z.db.gz"
    echo "  $0 /opt/marktrail/backups/marktrail_backup_20261023_120000Z.db.gz --force"
    exit 1
}

if [ $# -lt 1 ]; then
    usage
fi

BACKUP_FILE="$1"
FORCE="${2:-}"
DB_PATH="${MARKTRAIL_DB_PATH:-/opt/marktrail/data/marktrail.db}"
DB_DIR="$(dirname "$DB_PATH")"
TIMESTAMP="$(date -u +"%Y%m%d_%H%M%SZ")"

sqlite_exec() {
    local db_file="$1"
    local sql_cmd="$2"
    python3 -c "import sqlite3, sys; conn = sqlite3.connect(sys.argv[1]); res = conn.execute(sys.argv[2]).fetchall(); [print(r[0]) for r in res if r]; conn.commit(); conn.close()" "$db_file" "$sql_cmd"
}

if [ ! -f "$BACKUP_FILE" ]; then
    echo "ERROR: Specified backup file does not exist: ${BACKUP_FILE}"
    exit 1
fi

echo "=========================================================="
echo " MarkTrail Database Restore"
echo "=========================================================="
echo "Target database : ${DB_PATH}"
echo "Source backup   : ${BACKUP_FILE}"
echo ""

# 1. Unpack backup to temporary directory and test integrity
TEMP_DIR="$(mktemp -d /tmp/marktrail_restore_XXXXXX)"
trap 'rm -rf "$TEMP_DIR"' EXIT

RESTORE_STAGING="${TEMP_DIR}/staging.db"

if [[ "$BACKUP_FILE" == *.gz ]]; then
    echo "[1/5] Decompressing backup..."
    gzip -dc "$BACKUP_FILE" > "$RESTORE_STAGING"
else
    echo "[1/5] Copying backup to staging..."
    cp "$BACKUP_FILE" "$RESTORE_STAGING"
fi

echo "[2/5] Verifying staged database integrity..."
STAGE_CHECK=$(sqlite_exec "$RESTORE_STAGING" "PRAGMA integrity_check;" 2>&1)
if [ "$STAGE_CHECK" != "ok" ]; then
    echo "ERROR: Staged database failed integrity check: ${STAGE_CHECK}"
    echo "Aborting restore to protect existing database."
    exit 2
fi
echo "      Integrity check passed (ok)."

# 2. Safety confirmation
if [ "$FORCE" != "--force" ]; then
    echo ""
    echo "WARNING: Restoring will overwrite the current live database!"
    read -r -p "Are you sure you want to proceed? [y/N] " CONFIRM
    if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then
        echo "Restore cancelled by operator."
        exit 0
    fi
fi

# 3. Create pre-restore safety copy of the current live database
if [ -f "$DB_PATH" ]; then
    PRE_RESTORE_COPY="${DB_DIR}/marktrail.db.pre_restore_${TIMESTAMP}.bak"
    echo "[3/5] Saving pre-restore backup of live database to ${PRE_RESTORE_COPY}..."
    sqlite_exec "$DB_PATH" "VACUUM INTO '${PRE_RESTORE_COPY}';" || cp "$DB_PATH" "$PRE_RESTORE_COPY"
    chmod 600 "$PRE_RESTORE_COPY"
fi

# 4. Atomic replacement
echo "[4/5] Restoring database file..."
mkdir -p "$DB_DIR"
cp "$RESTORE_STAGING" "${DB_PATH}.tmp"
chmod 600 "${DB_PATH}.tmp"
mv -f "${DB_PATH}.tmp" "$DB_PATH"

# Set ownership if running as root
if [ "$(id -u)" -eq 0 ] && id "marktrail" &>/dev/null; then
    chown marktrail:marktrail "$DB_PATH"
fi

# 5. Final integrity check on the installed file
echo "[5/5] Running final integrity verification on restored database..."
FINAL_CHECK=$(sqlite_exec "$DB_PATH" "PRAGMA integrity_check;" 2>&1)
if [ "$FINAL_CHECK" != "ok" ]; then
    echo "CRITICAL ERROR: Restored database failed integrity check: ${FINAL_CHECK}"
    exit 3
fi

echo ""
echo "SUCCESS: Database restored successfully to ${DB_PATH}."
echo "If the MarkTrail service was stopped, restart it now via: systemctl restart marktrail"
