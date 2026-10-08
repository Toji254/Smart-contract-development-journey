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

Start with four roles:

- Student — views marks and reports missing assessments.
- Lecturer — submits marks and resolves reports.
- Reviewer — verifies submitted batches.
- Administrator — manages roles and institutional configuration.

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
- role-based access for students, lecturers, reviewers, and administrators;
- course and roster management;
- assessment creation;
- CSV validation and batch submission;
- missing-mark reports;
- lecturer resolution;
- controlled mark amendments;
- reviewer verification before publication;
- audit events;
- database/chain reconciliation hooks.

The application uses SQLite and only Python's standard library so the architecture stays easy to inspect.

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
verify
  ↓
published to students

STUDENT
  ↓
sees missing mark
  ↓
opens report

LECTURER
  ↓
enters mark / no mark
  ↓
new batch revision
  ↓
REVIEWER verifies amendment
  ↓
new value published
~~~

### Local development

~~~bash
cd MarkTrail
python3 run.py
~~~

Open http://127.0.0.1:8000.

Tests:

~~~bash
python3 -m unittest discover -s tests -v
forge build
forge test -vv
~~~

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
