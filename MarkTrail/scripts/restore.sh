#!/usr/bin/env bash
# Paired database + private evidence restore. Both archives are validated
# before the live database or evidence directory is replaced.
set -euo pipefail

usage() {
    echo "Usage: $0 <path-to-database-backup.db.gz> [--force]"
    echo "A matching marktrail_evidence_<timestamp>.tar.gz sidecar is required"
    echo "when the database contains the evidence_attachments table."
    exit 1
}
if [ $# -lt 1 ]; then usage; fi

BACKUP_FILE="$1"
FORCE="${2:-}"
DB_PATH="${MARKTRAIL_DB_PATH:-/opt/marktrail/data/marktrail.db}"
DB_DIR="$(dirname "$DB_PATH")"
EVIDENCE_DIR="${MARKTRAIL_EVIDENCE_DIR:-${DB_DIR}/private-evidence}"
TIMESTAMP="$(date -u +"%Y%m%d_%H%M%SZ")"

sqlite_exec() {
    local db_file="$1"
    local sql_cmd="$2"
    python3 -c "import sqlite3, sys; conn = sqlite3.connect(sys.argv[1]); res = conn.execute(sys.argv[2]).fetchall(); [print(r[0]) for r in res if r]; conn.commit(); conn.close()" "$db_file" "$sql_cmd"
}
if [ ! -f "$BACKUP_FILE" ]; then
    echo "ERROR: Database backup does not exist: ${BACKUP_FILE}"
    exit 1
fi
if [[ "$BACKUP_FILE" != *.db.gz ]]; then
    echo "ERROR: Expected a .db.gz MarkTrail database backup."
    exit 1
fi

BACKUP_NAME="$(basename "$BACKUP_FILE")"
BACKUP_STAMP="${BACKUP_NAME#marktrail_backup_}"
BACKUP_STAMP="${BACKUP_STAMP%.db.gz}"
EVIDENCE_BACKUP="$(dirname "$BACKUP_FILE")/marktrail_evidence_${BACKUP_STAMP}.tar.gz"

echo "=========================================================="
echo " MarkTrail Paired Database + Evidence Restore"
echo "=========================================================="
echo "Target database : ${DB_PATH}"
echo "Target evidence : ${EVIDENCE_DIR}"
echo "Source database : ${BACKUP_FILE}"
echo "Source evidence : ${EVIDENCE_BACKUP}"
echo ""

TEMP_DIR="$(mktemp -d /tmp/marktrail_restore_XXXXXX)"
trap 'rm -rf "$TEMP_DIR"' EXIT
RESTORE_STAGING="${TEMP_DIR}/staging.db"
STAGED_EVIDENCE="${TEMP_DIR}/private-evidence"
mkdir -m 700 "$STAGED_EVIDENCE"

echo "[1/6] Decompressing database backup..."
gzip -dc "$BACKUP_FILE" > "$RESTORE_STAGING"

echo "[2/6] Verifying staged database integrity..."
STAGE_CHECK="$(sqlite_exec "$RESTORE_STAGING" "PRAGMA integrity_check;" 2>&1)"
if [ "$STAGE_CHECK" != "ok" ]; then
    echo "ERROR: Staged database failed integrity check: ${STAGE_CHECK}"
    exit 2
fi
HAS_ATTACHMENT_TABLE="$(sqlite_exec "$RESTORE_STAGING" "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='evidence_attachments';")"

if [ -f "$EVIDENCE_BACKUP" ]; then
    echo "[3/6] Validating and safely extracting private evidence archive..."
    python3 - "$EVIDENCE_BACKUP" "$STAGED_EVIDENCE" "$RESTORE_STAGING" <<'PY'
import hashlib
import os
import re
import sqlite3
import stat
import sys
import tarfile

archive_path, destination, database_path = sys.argv[1], sys.argv[2], sys.argv[3]
allowed = re.compile(r"^[a-f0-9]{32}\.(?:pdf|png|jpg|jpeg)$")
total = 0
with tarfile.open(archive_path, "r:gz") as archive:
    for member in archive.getmembers():
        name = member.name
        if name in (".", "./"):
            continue
        if name.startswith("./"):
            name = name[2:]
        if not member.isfile() or "/" in name or not allowed.fullmatch(name):
            raise SystemExit(f"Unsafe evidence archive entry rejected: {member.name!r}")
        # AES-256-GCM envelope adds a fixed header, nonce and authentication tag.
        # Allow that small overhead while preserving the 10 MB plaintext limit.
        if member.size <= 0 or member.size > 10 * 1024 * 1024 + 128:
            raise SystemExit(f"Invalid evidence file size in archive: {member.name!r}")
        source = archive.extractfile(member)
        if source is None:
            raise SystemExit(f"Could not read evidence archive entry: {member.name!r}")
        target = os.path.join(destination, name)
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as output, source:
            while True:
                chunk = source.read(1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)
                total += len(chunk)
        if os.path.getsize(target) != member.size:
            raise SystemExit(f"Evidence archive entry was truncated: {member.name!r}")
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
            raise SystemExit("Restored database attachment schema is missing storage_key or byte_size.")
        selected = ["storage_key", "byte_size"]
        selected.append("encryption_version" if "encryption_version" in columns else "0")
        selected.append("sha256" if "sha256" in columns else "NULL")
        rows = connection.execute("SELECT " + ", ".join(selected) + " FROM evidence_attachments").fetchall()
finally:
    connection.close()

magic = b"MT-EVIDENCE-ENC1"
overhead = len(magic) + 12 + 16
maximum_plaintext = 10 * 1024 * 1024
for storage_key, byte_size, encryption_version, digest in rows:
    name = str(storage_key or "")
    if not allowed.fullmatch(name):
        raise SystemExit(f"Unsafe storage key in restored database: {name!r}")
    path = os.path.join(destination, name)
    if os.path.islink(path):
        raise SystemExit(f"Attachment file is a symlink in evidence archive: {name}")
    try:
        info = os.stat(path, follow_symlinks=False)
    except FileNotFoundError:
        raise SystemExit(f"Attachment file is missing from evidence archive: {name}")
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise SystemExit(f"Attachment is not a single-link regular file in evidence archive: {name}")
    size, version = int(byte_size), int(encryption_version or 0)
    if size <= 0 or size > maximum_plaintext:
        raise SystemExit(f"Invalid plaintext size in restored attachment metadata: {name}")
    encrypted_size = size + overhead
    if version == 1 and info.st_size != encrypted_size:
        raise SystemExit(f"Encrypted attachment size does not match database metadata: {name}")
    if version == 0 and info.st_size not in (size, encrypted_size):
        raise SystemExit(f"Legacy attachment size does not match database metadata: {name}")
    if version not in (0, 1) or info.st_size > maximum_plaintext + overhead:
        raise SystemExit(f"Unsupported or oversized evidence file in archive: {name}")
    if version == 1 or (version == 0 and info.st_size == encrypted_size):
        with open(path, "rb") as handle:
            if handle.read(len(magic)) != magic:
                raise SystemExit(f"Encrypted attachment header is invalid: {name}")
    elif digest:
        calculated = hashlib.sha256()
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                calculated.update(chunk)
        if calculated.hexdigest() != str(digest):
            raise SystemExit(f"Legacy plaintext attachment failed SHA-256 check: {name}")

print(
    f"Verified and extracted {len(os.listdir(destination))} evidence file(s), "
    f"{total} bytes; all {len(rows)} database attachment reference(s) exist."
)
PY
elif [ "$HAS_ATTACHMENT_TABLE" = "1" ]; then
    echo "ERROR: Database has evidence attachment records but the matching evidence archive is missing:"
    echo "       ${EVIDENCE_BACKUP}"
    echo "Refusing to restore records that would point to missing files."
    exit 3
else
    echo "[3/6] Legacy database has no attachment table; preparing an empty evidence directory."
fi

if [ "$FORCE" != "--force" ]; then
    echo ""
    echo "WARNING: Restoring overwrites the current database and private evidence directory."
    read -r -p "Are you sure you want to proceed? [y/N] " CONFIRM
    if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then
        echo "Restore cancelled by operator."
        exit 0
    fi
fi

mkdir -p "$DB_DIR" "$(dirname "$EVIDENCE_DIR")"
if [ -f "$DB_PATH" ]; then
    PRE_RESTORE_DB="${DB_DIR}/marktrail.db.pre_restore_${TIMESTAMP}.bak"
    echo "[4/6] Creating pre-restore database safety copy..."
    sqlite_exec "$DB_PATH" "VACUUM INTO '$PRE_RESTORE_DB';" || cp "$DB_PATH" "$PRE_RESTORE_DB"
    chmod 600 "$PRE_RESTORE_DB"
fi

NEW_EVIDENCE="${EVIDENCE_DIR}.restore_${TIMESTAMP}"
PRE_RESTORE_EVIDENCE="${EVIDENCE_DIR}.pre_restore_${TIMESTAMP}"
if [ -e "$NEW_EVIDENCE" ] || [ -e "$PRE_RESTORE_EVIDENCE" ]; then
    echo "ERROR: Restore safety path already exists; refusing to overwrite it."
    exit 4
fi
mkdir -m 700 "$NEW_EVIDENCE"
cp -a "$STAGED_EVIDENCE/." "$NEW_EVIDENCE/"
chmod 700 "$NEW_EVIDENCE"
find "$NEW_EVIDENCE" -type f -exec chmod 600 {} +

EVIDENCE_MOVED=0
if [ -d "$EVIDENCE_DIR" ]; then
    mv "$EVIDENCE_DIR" "$PRE_RESTORE_EVIDENCE"
    EVIDENCE_MOVED=1
fi
if ! mv "$NEW_EVIDENCE" "$EVIDENCE_DIR"; then
    if [ "$EVIDENCE_MOVED" = "1" ]; then mv "$PRE_RESTORE_EVIDENCE" "$EVIDENCE_DIR"; fi
    echo "ERROR: Could not install restored evidence directory; previous evidence was kept."
    exit 5
fi

echo "[5/6] Replacing database..."
if ! cp "$RESTORE_STAGING" "${DB_PATH}.tmp"; then
    rm -rf "$EVIDENCE_DIR"
    if [ "$EVIDENCE_MOVED" = "1" ]; then mv "$PRE_RESTORE_EVIDENCE" "$EVIDENCE_DIR"; fi
    echo "ERROR: Could not stage database; previous evidence was restored."
    exit 6
fi
chmod 600 "${DB_PATH}.tmp"
mv -f "${DB_PATH}.tmp" "$DB_PATH"

if [ "$(id -u)" -eq 0 ] && id "marktrail" &>/dev/null; then
    chown marktrail:marktrail "$DB_PATH"
    chown -R marktrail:marktrail "$EVIDENCE_DIR"
fi
chmod 700 "$EVIDENCE_DIR"
find "$EVIDENCE_DIR" -type f -exec chmod 600 {} +

echo "[6/6] Running final integrity verification..."
FINAL_CHECK="$(sqlite_exec "$DB_PATH" "PRAGMA integrity_check;" 2>&1)"
if [ "$FINAL_CHECK" != "ok" ]; then
    echo "CRITICAL ERROR: Restored database failed final integrity check: ${FINAL_CHECK}"
    echo "Pre-restore safety copies remain available for operator recovery."
    exit 7
fi

echo ""
echo "SUCCESS: database and matching private evidence archive restored."
if [ -n "${PRE_RESTORE_DB:-}" ]; then echo "Previous database: ${PRE_RESTORE_DB}"; fi
if [ "$EVIDENCE_MOVED" = "1" ]; then echo "Previous evidence: ${PRE_RESTORE_EVIDENCE}"; fi
echo "Restart MarkTrail when ready: systemctl restart marktrail"
