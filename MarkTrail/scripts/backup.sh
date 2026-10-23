#!/usr/bin/env bash
# ==============================================================================
# MarkTrail — Automated SQLite Online Database Backup Script
# Performs online atomic backup without interrupting running transactions.
# Uses Python's built-in sqlite3 engine (no external sqlite3 CLI required).
# ==============================================================================
set -euo pipefail

DB_PATH="${MARKTRAIL_DB_PATH:-/opt/marktrail/data/marktrail.db}"
BACKUP_DIR="${MARKTRAIL_BACKUP_DIR:-/opt/marktrail/backups}"
RETENTION_DAYS="${MARKTRAIL_BACKUP_RETENTION_DAYS:-14}"

TIMESTAMP="$(date -u +"%Y%m%d_%H%M%SZ")"
LOG_PREFIX="[marktrail-backup ${TIMESTAMP}]"

log() {
    echo "${LOG_PREFIX} $*"
}

sqlite_exec() {
    local db_file="$1"
    local sql_cmd="$2"
    python3 -c "import sqlite3, sys; conn = sqlite3.connect(sys.argv[1]); res = conn.execute(sys.argv[2]).fetchall(); [print(r[0]) for r in res if r]; conn.commit(); conn.close()" "$db_file" "$sql_cmd"
}

# 1. Validation
if [ ! -f "$DB_PATH" ]; then
    log "ERROR: Database file not found at ${DB_PATH}"
    exit 1
fi

mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"

# 2. Source database integrity check
log "Running pre-backup integrity check on source database..."
INTEGRITY=$(sqlite_exec "$DB_PATH" "PRAGMA integrity_check;" 2>&1)
if [ "$INTEGRITY" != "ok" ]; then
    log "ERROR: Source database failed integrity check: ${INTEGRITY}"
    exit 2
fi
log "Source database integrity verified: ok"

# 3. Perform atomic online backup using VACUUM INTO
TEMP_SNAPSHOT="${BACKUP_DIR}/.snapshot_${TIMESTAMP}.db"
FINAL_FILE="${BACKUP_DIR}/marktrail_backup_${TIMESTAMP}.db.gz"

log "Creating atomic snapshot via VACUUM INTO..."
sqlite_exec "$DB_PATH" "VACUUM INTO '${TEMP_SNAPSHOT}';"

# 4. Verify snapshot integrity before compressing
log "Verifying snapshot integrity..."
SNAPSHOT_INTEGRITY=$(sqlite_exec "$TEMP_SNAPSHOT" "PRAGMA integrity_check;" 2>&1)
if [ "$SNAPSHOT_INTEGRITY" != "ok" ]; then
    log "ERROR: Backup snapshot failed integrity check: ${SNAPSHOT_INTEGRITY}"
    rm -f "$TEMP_SNAPSHOT"
    exit 3
fi

# 5. Compress snapshot
log "Compressing backup snapshot..."
gzip -c "$TEMP_SNAPSHOT" > "$FINAL_FILE"
chmod 600 "$FINAL_FILE"
rm -f "$TEMP_SNAPSHOT"

BACKUP_SIZE=$(du -h "$FINAL_FILE" | cut -f1)
log "Backup completed successfully: ${FINAL_FILE} (${BACKUP_SIZE})"

# 6. Apply retention policy (prune backups older than RETENTION_DAYS)
log "Pruning backups older than ${RETENTION_DAYS} days..."
find "$BACKUP_DIR" -name "marktrail_backup_*.db.gz" -type f -mtime +"${RETENTION_DAYS}" -delete
REMAINING_COUNT=$(find "$BACKUP_DIR" -name "marktrail_backup_*.db.gz" -type f | wc -l)
log "Retention pruning complete. ${REMAINING_COUNT} backup(s) stored in ${BACKUP_DIR}."
