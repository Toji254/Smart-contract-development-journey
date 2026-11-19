#!/usr/bin/env bash
# Paired SQLite + private evidence backup. Files are written before their
# attachment row commits, so the later file archive covers every row in the
# earlier database snapshot (it may also contain an unreferenced newer file).
set -euo pipefail

DB_PATH="${MARKTRAIL_DB_PATH:-/opt/marktrail/data/marktrail.db}"
BACKUP_DIR="${MARKTRAIL_BACKUP_DIR:-/opt/marktrail/backups}"
EVIDENCE_DIR="${MARKTRAIL_EVIDENCE_DIR:-$(dirname "$DB_PATH")/private-evidence}"
RETENTION_DAYS="${MARKTRAIL_BACKUP_RETENTION_DAYS:-14}"
TIMESTAMP="$(date -u +"%Y%m%d_%H%M%SZ")"
LOG_PREFIX="[marktrail-backup ${TIMESTAMP}]"

log() { echo "${LOG_PREFIX} $*"; }
sqlite_exec() {
    local db_file="$1"
    local sql_cmd="$2"
    python3 -c "import sqlite3, sys; conn = sqlite3.connect(sys.argv[1]); res = conn.execute(sys.argv[2]).fetchall(); [print(r[0]) for r in res if r]; conn.commit(); conn.close()" "$db_file" "$sql_cmd"
}

if [ ! -f "$DB_PATH" ]; then
    log "ERROR: Database file not found at ${DB_PATH}"
    exit 1
fi
mkdir -p "$BACKUP_DIR" "$EVIDENCE_DIR"
chmod 700 "$BACKUP_DIR" "$EVIDENCE_DIR"

TEMP_SNAPSHOT="${BACKUP_DIR}/.snapshot_${TIMESTAMP}.db"
TEMP_DB_ARCHIVE="${BACKUP_DIR}/.marktrail_backup_${TIMESTAMP}.db.gz.tmp"
TEMP_EVIDENCE_ARCHIVE="${BACKUP_DIR}/.marktrail_evidence_${TIMESTAMP}.tar.gz.tmp"
FINAL_DB_ARCHIVE="${BACKUP_DIR}/marktrail_backup_${TIMESTAMP}.db.gz"
FINAL_EVIDENCE_ARCHIVE="${BACKUP_DIR}/marktrail_evidence_${TIMESTAMP}.tar.gz"
cleanup() {
    rm -f "$TEMP_SNAPSHOT" "$TEMP_DB_ARCHIVE" "$TEMP_EVIDENCE_ARCHIVE"
}
trap cleanup EXIT

log "Running pre-backup database integrity check..."
INTEGRITY="$(sqlite_exec "$DB_PATH" "PRAGMA integrity_check;" 2>&1)"
if [ "$INTEGRITY" != "ok" ]; then
    log "ERROR: Source database failed integrity check: ${INTEGRITY}"
    exit 2
fi

log "Creating atomic online database snapshot..."
sqlite_exec "$DB_PATH" "VACUUM INTO '$TEMP_SNAPSHOT';"
SNAPSHOT_INTEGRITY="$(sqlite_exec "$TEMP_SNAPSHOT" "PRAGMA integrity_check;" 2>&1)"
if [ "$SNAPSHOT_INTEGRITY" != "ok" ]; then
    log "ERROR: Snapshot failed integrity check: ${SNAPSHOT_INTEGRITY}"
    exit 3
fi

log "Archiving private evidence files from ${EVIDENCE_DIR}..."
tar -czf "$TEMP_EVIDENCE_ARCHIVE" -C "$EVIDENCE_DIR" .
tar -tzf "$TEMP_EVIDENCE_ARCHIVE" >/dev/null
chmod 600 "$TEMP_EVIDENCE_ARCHIVE"

log "Compressing database snapshot..."
gzip -c "$TEMP_SNAPSHOT" > "$TEMP_DB_ARCHIVE"
chmod 600 "$TEMP_DB_ARCHIVE"

# Publish evidence first; a visible DB backup always has its sidecar.
mv -f "$TEMP_EVIDENCE_ARCHIVE" "$FINAL_EVIDENCE_ARCHIVE"
mv -f "$TEMP_DB_ARCHIVE" "$FINAL_DB_ARCHIVE"
rm -f "$TEMP_SNAPSHOT"

DB_SIZE="$(du -h "$FINAL_DB_ARCHIVE" | cut -f1)"
EVIDENCE_SIZE="$(du -h "$FINAL_EVIDENCE_ARCHIVE" | cut -f1)"
log "Database backup: ${FINAL_DB_ARCHIVE} (${DB_SIZE})"
log "Evidence archive: ${FINAL_EVIDENCE_ARCHIVE} (${EVIDENCE_SIZE})"
log "Paired backup completed successfully."

log "Pruning backups older than ${RETENTION_DAYS} days..."
find "$BACKUP_DIR" -name "marktrail_backup_*.db.gz" -type f -mtime +"${RETENTION_DAYS}" -delete
find "$BACKUP_DIR" -name "marktrail_evidence_*.tar.gz" -type f -mtime +"${RETENTION_DAYS}" -delete
DB_COUNT="$(find "$BACKUP_DIR" -name "marktrail_backup_*.db.gz" -type f | wc -l)"
EVIDENCE_COUNT="$(find "$BACKUP_DIR" -name "marktrail_evidence_*.tar.gz" -type f | wc -l)"
log "Retention complete. ${DB_COUNT} database and ${EVIDENCE_COUNT} evidence archives remain."
