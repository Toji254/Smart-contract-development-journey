# MarkTrail

> A prototype for making academic marks traceable from lecturer submission to student resolution.

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
