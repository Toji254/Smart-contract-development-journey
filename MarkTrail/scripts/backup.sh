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

log "Checking database snapshot references against private evidence files..."
python3 - "$TEMP_SNAPSHOT" "$EVIDENCE_DIR" <<'PY'
import hashlib
import os
import re
import sqlite3
import stat
import sys

database_path, evidence_root = sys.argv[1], sys.argv[2]
allowed = re.compile(r"^[a-f0-9]{32}\.(?:pdf|png|jpg|jpeg)$")
magic = b"MT-EVIDENCE-ENC1"
overhead = len(magic) + 12 + 16
maximum_plaintext = 10 * 1024 * 1024
connection = sqlite3.connect(database_path)
try:
    exists = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='evidence_attachments'"
    ).fetchone()
    if not exists:
        rows = []
    else:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(evidence_attachments)")}
        if not {"storage_key", "byte_size"}.issubset(columns):
            raise SystemExit("Evidence attachment schema is missing storage_key or byte_size.")
        selected = ["storage_key", "byte_size"]
        selected.append("encryption_version" if "encryption_version" in columns else "0")
        selected.append("sha256" if "sha256" in columns else "NULL")
        rows = connection.execute("SELECT " + ", ".join(selected) + " FROM evidence_attachments").fetchall()
finally:
    connection.close()

for storage_key, byte_size, encryption_version, digest in rows:
    name = str(storage_key or "")
    if not allowed.fullmatch(name):
        raise SystemExit(f"Unsafe attachment storage key in database snapshot: {name!r}")
    path = os.path.join(evidence_root, name)
    if os.path.islink(path):
        raise SystemExit(f"Referenced evidence file is a symlink: {name}")
    try:
        info = os.stat(path, follow_symlinks=False)
    except FileNotFoundError:
        raise SystemExit(f"Referenced evidence file is missing: {name}")
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise SystemExit(f"Referenced evidence file is not a single-link regular file: {name}")
    size, version = int(byte_size), int(encryption_version or 0)
    if size <= 0 or size > maximum_plaintext:
        raise SystemExit(f"Invalid plaintext size in attachment metadata: {name}")
    encrypted_size = size + overhead
    if version == 1 and info.st_size != encrypted_size:
        raise SystemExit(f"Encrypted evidence size does not match metadata: {name}")
    if version == 0 and info.st_size not in (size, encrypted_size):
        raise SystemExit(f"Legacy evidence size does not match metadata: {name}")
    if version not in (0, 1) or info.st_size > maximum_plaintext + overhead:
        raise SystemExit(f"Unsupported or oversized evidence file: {name}")
    if version == 1 or (version == 0 and info.st_size == encrypted_size):
        with open(path, "rb") as handle:
            if handle.read(len(magic)) != magic:
                raise SystemExit(f"Encrypted evidence header is invalid: {name}")
    elif digest:
        calculated = hashlib.sha256()
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                calculated.update(chunk)
        if calculated.hexdigest() != str(digest):
            raise SystemExit(f"Legacy plaintext evidence failed its SHA-256 check: {name}")

print(f"Validated {len(rows)} database attachment reference(s).")
PY

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
