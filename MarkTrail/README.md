# MarkTrail

> A full-stack MVP for making academic marks traceable from lecturer submission to student resolution.

MarkTrail starts from a simple problem:

> **A student discovers a missing mark, but nobody can clearly tell where the mark disappeared or what happened to it.**

The prototype separates the product into two parts:

1. **Application layer** — the normal student/lecturer workflow and private marks data.
2. **Audit layer** — a small Solidity contract that records cryptographic commitments and a revision history without putting actual marks on-chain.

## Prototype flow

```text
LECTURER
   |
   | submit marks batch
   v
MARKTRAIL APP
   |
   +--> private database (actual marks)
   |
   +--> audit hash
          |
          v
      MARKTRAIL AUDIT CONTRACT

STUDENT
   |
   | sees mark status
   v
MISSING MARK?
   |
   +--> report once
          |
          v
LECTURER ISSUE QUEUE
   |
   +--> enter mark
   +--> confirm no mark
          |
          v
      resolution + history
```

## What is working in this prototype

### Student side

- View assessment status for a sample course.
- See a missing mark immediately.
- Report the missing mark once.
- See the issue move into a resolution workflow.

### Lecturer side

- See missing-mark reports in one queue.
- Resolve a report by entering a mark.
- Confirm that no mark was awarded.
- See a simple audit history for submissions and amendments.

### Solidity audit layer

`src/MarkTrailAudit.sol` demonstrates the on-chain part of the design.

It records:

- course and assessment identifiers
- the number of students represented by a batch
- a commitment/hash for the marks batch
- who submitted it
- when it was submitted
- who verified it
- later amendment commitments
- the complete revision trail

**Actual marks are deliberately not stored on-chain.**

A real deployment would keep the actual marks in a protected application database and use the blockchain only as a tamper-evident audit layer.

Contract administration uses OpenZeppelin's two-step ownership transfer: the proposed
owner must call `acceptOwnership()` before control changes. Lecturer and reviewer
permissions remain owner-managed allowlists through `setLecturer` and `setReviewer`.
Existing deployed instances are not upgradeable; deploy the updated contract and
configure the application to use its new address.

## Important security note

A plain hash is not automatically private.

Marks have a small and predictable value space, so publishing a hash of something like:

`studentId + course + mark`

could allow guessing attacks.

A production implementation should use a proper commitment design with a cryptographically random salt/nonce and a carefully defined canonical encoding. This prototype intentionally keeps that cryptographic boundary visible so it can be audited and improved rather than pretending the hash alone solves privacy.

## Running the UI prototype

From this directory:

```bash
python3 -m http.server 8000 --directory prototype
```

Then open:

`http://127.0.0.1:8000`

The UI uses local browser state only. It does **not** contain real student data and does **not** submit blockchain transactions yet.

## Running the Solidity tests

From this directory:

```bash
forge test -vv
```

The test suite is deliberately dependency-light so the contract can be studied without hiding the logic behind a framework.

## Current scope

This is a **prototype, not a production academic records system**.

Not included yet:

- university authentication / SSO
- real student records
- real database
- real blockchain RPC connection
- wallet or gas management
- role administration UI
- privacy-preserving proofs
- university integrations
- legal/privacy compliance
- independent security review

The next design question is not “how do we add more blockchain?”

It is:

> **At which points in the real marks pipeline does an independently verifiable audit record actually reduce disputes or administrative work?**

That question should drive the next version.

## MarkTrail examination query and workbook pilot

The runnable application now also provides:

- individual lecturer accounts and course/co-lecturer authorization;
- immutable roster snapshots and protected `.xlsx` marks workbooks;
- server-side workbook validation for identity, duplicates, unknown candidates,
  missing candidates, numeric ranges, formulas and explicit outcomes;
- Academic Registry registration exceptions with registry-only decisions;
- student-owned examination query cases and staff assignment queues;
- audit events and in-app notifications for registration and case decisions;
- role-scoped staff and student APIs, with standalone demo accounts for local use.

This is a pilot implementation. KarU SSO, official registration feeds and
production email/SMS providers are integration boundaries and are not enabled.


## Project path

This is the build path for MarkTrail. Follow it in order. The point is to understand the system before adding complexity.

### 1. Define the problem

Map how a mark currently moves through the institution:

~~~text
Lecturer → Department → Exam / Academic Office → Portal → Student
~~~

For every stage, identify:

- what information is created;
- who controls it;
- who can change it;
- how submission is acknowledged;
- what evidence remains if something goes wrong.

The first version should solve one concrete problem: a student can report a missing mark and the institution can trace the issue to a resolution.

### 2. Define the actors

The initial application used four roles:

- Student — views marks and reports missing assessments.
- Lecturer — submits marks and resolves reports.
- Reviewer — verifies submitted batches.
- Administrator — manages roles and institutional configuration.

The runnable MVP also separates department review from later handoffs:
reviewers represent the department/HOD, while exam-office staff and portal
operators record their own processing steps.

Authorization must be enforced by the application and, where applicable, the smart contract. Hiding a button is not access control.

### 3. Define the core data

The application will eventually need concepts such as:

~~~text
Student
Course
Assessment
Mark
MarksBatch
MissingMarkReport
Resolution
AuditRecord
~~~

A report should make it possible to answer who reported it, which student and assessment it concerns, when it was opened, its current status, who resolved it, and what the outcome was.

### 4. Design the workflow before coding

Core student flow:

~~~text
SEE MARKS
   ↓
MISSING?
   ↓
REPORT
   ↓
OPEN
   ↓
UNDER REVIEW
   ↓
RESOLVED
~~~

Core lecturer flow:

~~~text
PREPARE MARKS
   ↓
VALIDATE
   ↓
SUBMIT BATCH
   ↓
RESOLVE EXCEPTIONS
   ↓
AMEND WHEN NECESSARY
~~~

Write down every allowed state transition before implementing the contract.

### 5. Build the application first

The first UI should work without wallets or blockchain transactions.

Build:

- student assessment status;
- missing-mark reporting;
- lecturer issue queue;
- mark resolution;
- resolution history;
- basic submission history.

This proves that the human workflow is useful before blockchain complexity is introduced.

### 6. Build the Solidity audit layer

The first smart contract should have a narrow responsibility:

~~~text
batch submission
      ↓
verification
      ↓
amendment
      ↓
permanent revision history
~~~

It should not become the entire marks database.

The contract should record commitments to batches, not actual student marks.

### 7. Understand the commitment

The application should create a canonical representation of a marks batch and derive a cryptographic commitment from it.

Do not simply concatenate predictable values and call the result private. A production scheme must consider random salts, canonical encoding, guessing attacks, and how a later verifier reconstructs exactly what was committed.

The important invariant is:

> The application must be able to prove which exact version of a batch was committed without publishing the students' marks.

Before publishing, MarkTrail rebuilds the canonical marks from the current
candidate records and recomputes the latest salted commitment. It also checks
the on-chain course, assessment, and student count. Each new revision stores
its own salt and canonical snapshot for later verification. Existing amended
history without saved revision salts cannot be reconstructed; those records
fail closed until their audit history can be independently restored.
These local commitment checks also run when blockchain integration is off;
local-only reconciliation reports that no independent on-chain anchor exists.
Publication repeats the marks check in the write transaction, and later
reconciliation checks that published marks still match the committed revision.

### 8. Test the contract

Start with ordinary tests:

- authorized lecturer can submit;
- unauthorized caller cannot submit;
- duplicate batch submission fails;
- authorized reviewer can verify;
- unauthorized reviewer cannot verify;
- amendment requires the correct state;
- every amendment preserves the previous revision;
- invalid identifiers and empty commitments fail.

Then move to fuzzing, invariant testing, Slither review, and manual attack scenarios.

### 9. Define the important security invariants

The protocol should always preserve rules such as:

~~~text
A student cannot become a lecturer.

An unauthorized account cannot submit a batch.

An unauthorized account cannot verify a batch.

A verified revision cannot be silently erased.

A mark amendment must leave an audit history.

A missing-mark report cannot be resolved twice.
~~~

Add tests for these invariants rather than assuming the happy path is enough.

### 10. Connect the application and chain

Only after the local application and contract work independently should the backend connect them.

~~~text
Frontend
   ↓
Backend
   ├── private database
   │      ↓
   │   actual marks
   │
   └── MarkTrailAudit
          ↓
       commitments
~~~

The blockchain transaction should be an implementation detail for normal users.

### 11. Handle discrepancies

A production system must be able to detect cases where:

~~~text
database record ≠ committed record
~~~

That mismatch should become an explicit operational issue instead of being silently overwritten.

### 12. Validate with people

Do not start with a university-wide deployment.

Start with synthetic data and a small pilot. Watch a few students and at least one lecturer use the workflow. The questions are:

- Did students understand what was missing?
- Did reporting remove the need to chase people?
- Did lecturers find the issue queue useful?
- Did the audit trail make disputes easier to explain?
- What part of the current university process did the prototype misunderstand?

Real user feedback should change the design.

## What MarkTrail aims to become

The first target is missing marks.

The longer-term aim is broader: make academic records traceable, easier to reconcile, and harder to alter silently.

~~~text
Missing marks
     ↓
Mark submissions
     ↓
Amendments
     ↓
Academic record history
     ↓
Transcript / certificate verification
~~~

That expansion should only happen after the original problem is genuinely solved.

## What success looks like

### Student

> I reported my missing mark once, I could see what was happening, and I did not have to chase multiple people.

### Lecturer

> I can see what I submitted and handle missing-mark reports in one place.

### Administrator

> When something goes wrong, we can identify where it happened instead of guessing.

## Development rule

Build the smallest complete path first.

~~~text
problem
   ↓
workflow
   ↓
application prototype
   ↓
Solidity audit layer
   ↓
tests
   ↓
attack the assumptions
   ↓
real-user validation
   ↓
only then expand
~~~

The project is not successful because it uses blockchain.

It is successful when MarkTrail makes the missing-mark problem materially easier for students, lecturers, and academic administrators.

## Full MVP implementation

The project now includes a complete runnable local stack rather than only a visual mock.

### Application layer

The Python application provides:

- session-based login;
- role-based access for students, lecturers, department reviewers, exam-office staff, portal operators, and administrators;
- course and roster management;
- assessment creation;
- CSV validation and batch submission;
- missing-mark reports;
- lecturer resolution or rejection with a recorded reason;
- controlled mark amendments;
- department review, exam-office processing, and portal import before publication;
- audit events;
- database/chain reconciliation hooks.

The application uses SQLite and Python's standard library for its core workflow.
Evidence encryption uses the maintained `cryptography` package (AES-256-GCM).

### Blockchain layer

The Solidity contract is MarkTrailAudit.

It provides:

- owner management;
- lecturer authorization;
- reviewer authorization;
- batch commitment submission;
- verification;
- amendment revisions;
- permanent revision history;
- events and custom errors.

The backend can use Foundry's cast command to write to and read from any configured EVM RPC.

### End-to-end lifecycle

~~~text
ADMIN
  ↓
create users / course / roster / assessments

LECTURER
  ↓
validate CSV
  ↓
submit batch
  ↓
chain commitment
  ↓
REVIEWER
  ↓
department review
  ↓
EXAM OFFICE
  ↓
record processing
  ↓
PORTAL OPERATOR
  ↓
import and publish
  ↓
STUDENT
  ↓
sees published mark

STUDENT
  ↓
reports missing mark
  ↓
LECTURER
  ↓
enter mark / no mark / reject with reason
  ↓
reviewer → exam office → portal import
  ↓
updated mark published
~~~

Reviewer approval is not the same as publication. Students only see a new or
amended mark after the portal operator records the import. Each handoff is
timestamped in the audit trail. A rejected report is closed with a reason; if
the mark is still missing, the student can open a new report.

When a chain update is retried, MarkTrail compares every saved revision's
marks and amendment reason with the recorded contract history, then checks
that the local workflow status agrees with the contract status. The initial
submission intentionally uses a zero on-chain reason hash. Missing revisions
can be replayed in order; inconsistent history or status is flagged for
administrator reconciliation rather than reported as recovered. Each replayed
revision retains its own transaction reference. State-changing transactions are
broadcast once and checked by transaction hash; if confirmation is uncertain,
the batch remains pending and recovery checks that transaction's receipt before
submitting another one.

The contract uses two-step ownership transfer and does not permit ownership
renunciation, so the contract cannot be left without an administrator.

### Private examination evidence attachments

Students can attach supporting files to their own open evidence cases. Authorised
staff can attach scanned source records to an examination session or an
individual script, including an unidentified script waiting for candidate
matching. Supported file types are PDF, PNG and JPEG, up to 10 MB per file.

Files are stored outside the web root under `MARKTRAIL_EVIDENCE_DIR` (or
`private-evidence` beside the database by default), using generated storage
keys and restricted filesystem permissions. File contents are encrypted at rest
with AES-256-GCM before they are written; the original filename is metadata,
not a storage path. The encryption key is supplied through
`MARKTRAIL_EVIDENCE_ENCRYPTION_KEY`, never stored in SQLite or the evidence
archive. New uploads fail closed when the key is not configured. When a key is
configured, legacy plaintext attachments are integrity-checked and encrypted
during service startup. Access is checked again on every list and download request.

A clean ClamAV scan is required before download. If ClamAV is missing,
unavailable or times out, the file remains quarantined and downloads are
blocked. Every download rechecks the byte count and SHA-256 digest. Attachment
metadata is immutable; upload, scan, rescan and integrity events are retained
in append-only history. Files, contents and hashes stay off-chain.

Assigned academic staff can manually request local document extraction for a
clean attachment. Tesseract handles PNG/JPEG; PDF OCR uses Tesseract plus
Poppler utilities (`pdfinfo` and `pdftoppm`). Extraction is optional and
requires the evidence encryption key. OCR text and suggestions are encrypted
before they enter SQLite. MarkTrail limits image dimensions to 40 megapixels,
PDF processing to the first five pages, and extracted text to 24,000
characters. The staff workspace presents possible document type, registration
references, dates and keyword hits as suggestions only. Every result requires
comparison with the original document and locked roster; OCR never changes
attendance, marks, student identity, script custody or case decisions. Missing
OCR tools are reported as unavailable rather than as a successful extraction.

The analysis endpoint is `POST /api/evidence/attachments/{attachment_id}/analyze`.
It rechecks the user's role and attachment ownership and refuses files that
have not passed the malware scan.

Database backups now have matching evidence sidecar archives. Both files must
be retained and restored as a pair. Before publishing a backup, MarkTrail checks
that every attachment row in the database snapshot points to a safe file with
the expected stored size. Restore repeats that cross-check against the extracted
archive and refuses to replace live data if even one referenced file is missing
or does not match its recorded size. Legacy plaintext files are also checked
against their SHA-256 digest before a backup or restore is accepted.

### Handoff tracking, notifications, and reports

The audit view shows the current handoff owner, how long the batch has waited,
and the recorded duration and handler for earlier stages. Students receive
in-app notifications when a report is rejected, a lecturer submits an
amendment, or marks are published. They can mark each notification as read.

Authorized users can download a CSV audit report for a batch. It includes
workflow events and stage timing; mark-level history is available only to
non-student roles.

Portal import is still recorded manually by a portal operator. Automatic
verification is not implemented. It needs an institution-approved API or
sandbox, its documentation, and authorized non-production access; do not use
personal portal passwords or session cookies.

### Local development

Install the one runtime dependency:

~~~bash
cd MarkTrail
python3 -m pip install -r requirements.txt
~~~

Generate a persistent local evidence key once. Keep it unchanged while any
encrypted evidence exists:

~~~bash
python3 -c 'import secrets; print(secrets.token_hex(32))'
~~~

Put the output in your local environment as
`MARKTRAIL_EVIDENCE_ENCRYPTION_KEY`. Do not commit the key or place it in a
database backup.

~~~bash
MARKTRAIL_EVIDENCE_ENCRYPTION_KEY="PASTE_YOUR_64_HEX_CHARACTER_KEY" MARKTRAIL_SEED_DEMO=1 MARKTRAIL_COOKIE_SECURE=0 python3 run.py
~~~

Open http://127.0.0.1:8000.

Demo accounts:

~~~text
student / student123
lecturer / lecturer123
reviewer / reviewer123
exam_office / office123
senate_office / senate123
portal_operator / portal123
admin / admin123
~~~

The demo course includes a fresh assessment named `CAT 3 (Ready to upload)` so
the lecturer can try CSV validation and batch submission immediately. CSV files
use the headers `registration_number,mark`; students omitted from a valid CSV
are recorded as missing. Common exports using `Registration Number,Marks` are
also accepted. Registration numbers must match students enrolled in the selected
course; names are not required in the marks CSV.

Assessments have an explicit result-release policy:
- `DIRECT` is for CATs/coursework that the university authorises for direct release.
- `SENATE` routes the verified batch from the exam office to the Senate Secretariat.
  The Secretariat records an approval or deferral against a meeting/minute reference.
  Deferred or pending batches are not available to the portal operator.
- Existing assessments from older databases are migrated as `UNCLASSIFIED`.
  An administrator must explicitly classify them before exam-office processing or
  portal publication can continue.

The synthetic demo `Final Exam` uses the Senate path and is seeded with a clearly
labelled synthetic Senate approval so the portal publication flow can be tested.
The demo `senate_office / senate123` account is only for local development.

The server defaults to no demo data and HTTPS-only session cookies. The
command above explicitly opts into synthetic demo accounts and an insecure
cookie for local HTTP only. Never use demo accounts or disable secure cookies
in an externally accessible deployment.

Only administrator-created accounts can sign in; there is no public sign-up.
New student accounts require a graduation/access end date, and the system
blocks sign-in and existing sessions after that date. Administrators can also
disable or re-enable any account from Setup. Existing accounts with no end date
remain active until an administrator sets one or disables the account.
Bulk enrollment creates a different high-entropy, one-time password for each
new student and displays it once for secure distribution by the institution.
The credential list is not stored by MarkTrail; students must change their
password at first sign-in.

For a new installation without demo users, create the first administrator
interactively with `python3 run.py --create-admin`, then start the server with
demo seeding disabled. The command prompts for the username, name, and
password; the password is not passed on the command line.

### Production readiness

Safe defaults do not make the current server production-ready. It uses
Python's built-in HTTP server and SQLite, and portal imports are still entered
manually. Do not store real student records in this deployment. A production
launch still needs an institution-approved hosting and database design,
HTTPS termination, backups and recovery testing, operational monitoring,
an independent security/privacy review, and operational processes for keeping
graduation dates and account approvals accurate.
Portal automation also requires an approved university API and test
environment.

Tests:

~~~bash
python3 -m unittest discover -s tests -v
forge build
forge test -vv
~~~

For a local demo database initialization or reset, opt in explicitly with
`python3 run.py --init --seed-demo` or `make reset`. Initialization and server
startup do not seed demo credentials by default.

### Chain configuration

The default mode is local-only. Set these variables to enable Foundry-backed chain writes:

~~~text
MARKTRAIL_CHAIN_MODE=cast
MARKTRAIL_CHAIN_RPC=http://127.0.0.1:8545
MARKTRAIL_CONTRACT=0x...
MARKTRAIL_CHAIN_PRIVATE_KEY=0x...
~~~

For a real institutional deployment, the single server-side signing key used by this MVP must be replaced by appropriate institutional custody, role separation, monitoring, and operational controls.

### What this aims to become

MarkTrail starts by solving missing marks.

The longer-term purpose is to make academic records traceable enough that students, lecturers, and administrators can answer three questions quickly:

1. What was submitted?
2. What changed?
3. Where did the failure happen?

The project should earn the right to expand only after the missing-mark workflow works for real users.
