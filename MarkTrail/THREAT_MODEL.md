# MarkTrail threat model

MarkTrail handles academic records, so the security model is more important than the blockchain brand.

## Assets

The system must protect:

- student identity and enrollment information;
- current and historical marks;
- lecturer submissions;
- reviewer approvals;
- amendment history;
- session credentials;
- blockchain signing credentials;
- the integrity relationship between the private database and on-chain commitments.

## Trust boundaries

~~~text
Student browser
      |
      | HTTPS / session
      v
MarkTrail API
   |          |
   |          +---- SQLite / production DB
   |
   +---- chain signer
             |
             v
        EVM contract
~~~

The browser is untrusted.

The application enforces institutional authorization.

The smart contract provides an additional independent audit boundary.

## Main threats

### Unauthorized mark changes

A student, attacker, or compromised account must not be able to change candidate or published marks through the application.

The contract must also reject unauthorized lecturer/reviewer calls.

### Privilege escalation

Changing a browser role or hiding UI controls must never be enough to obtain lecturer, reviewer, or admin privileges.

### Silent amendments

An approved mark must never be silently overwritten.

Every amendment should create:

~~~text
old published state
        ↓
new candidate state
        ↓
new commitment
        ↓
reviewer verification
        ↓
new published state
~~~

### Replay and duplicate actions

The system must reject duplicate batch identifiers and prevent repeated open reports for the same student and assessment.

### Database / chain divergence

The database and chain are separate systems and can disagree after process or infrastructure failures.

MarkTrail therefore tracks chain state and exposes reconciliation.

### Commitment guessing

Academic marks have a low entropy value domain.

A predictable hash input can be guessed.

Every batch revision therefore needs a random salt and a canonical encoding. The salt remains private.

### Compromised chain signer

The development MVP uses one configured server-side signing key.

That key is a high-value secret.

A production deployment should use institutional custody and stronger role separation rather than treating the MVP key model as production-ready.

### Malicious CSV uploads

CSV data is untrusted input.

The application validates:

- required headers;
- enrolled student IDs;
- duplicates;
- numeric marks;
- maximum marks.

### Session compromise

Sessions must be protected by secure cookies, HTTPS, expiration, and production-grade session management before real deployment.

## Security invariant

The most important product-level rule is:

> **A student should never see an amended mark as final until the amended batch has passed the required review step.**

The important contract-level rule is:

> **A verified revision cannot be silently erased; later amendments append to the revision history.**

## Prototype boundary

This threat model is for the development MVP.

It does not replace:

- an institutional security architecture;
- penetration testing;
- privacy/legal review;
- an independent smart-contract audit;
- secure production key management.
