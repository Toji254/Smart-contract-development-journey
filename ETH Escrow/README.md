# ETH Escrow

This project is a small ETH escrow contract and the first project in this repository that should be treated as a serious **state-machine + security** exercise.

The original project brief is preserved in:

`## 🥊 Solidity Weekly Challenge #1 — ETH.md`

---

## 1. What this contract is supposed to do

Two parties agree to an ETH payment:

- **Creator** deposits ETH.
- **Recipient** accepts the escrow.
- **Creator** releases the payment.
- **Recipient** receives the ETH.

The contract acts as the middleman.

Conceptually:

```
Creator
  |
  | deposit ETH
  v
Escrow contract
  |
  | recipient accepts
  v
ACCEPTED
  |
  | creator releases
  v
Recipient
```

A real implementation also needs a cancellation path.

---

## 2. Required behavior

### Create

A creator creates an escrow while sending ETH.

The escrow should store at least:

- creator;
- recipient;
- amount;
- status;
- unique identifier.

A valid implementation should prevent obviously invalid setup, such as invalid participants or a mismatch between the intended amount and the ETH actually deposited.

### Accept

Only the intended recipient may accept.

Expected transition:

```
CREATED -> ACCEPTED
```

### Release

Only the creator may release.

Release must only be possible after acceptance.

Expected transition:

```
ACCEPTED -> RELEASED
```

The escrowed ETH should be sent to the recipient exactly once.

### Cancel

Define explicit cancellation rules.

At minimum decide:

- who may cancel;
- from which states;
- whether the recipient/creator gets the funds;
- what the resulting state is.

### Events

Emit useful events for:

- creation;
- acceptance;
- release;
- cancellation.

---

## 3. Historical implementation: what to notice

The current source file is intentionally kept as historical material.

It contains several important learning clues:

- `escrow[1]` is hard-coded, so there is effectively only one escrow slot;
- a function parameter named `amount` is modified locally but the stored amount comes from `msg.value`;
- `balances[msg.sender]` is updated without being part of a coherent escrow accounting model;
- rejection attempts to mutate state and then reverts;
- release does not verify that the escrow was accepted;
- release does not mark the escrow as released;
- repeated releases are not explicitly blocked;
- cancellation is missing;
- input validation is incomplete;
- there is almost no automated test coverage.

Do not patch these one by one first.

**Rebuild from the brief.**

That forces the state machine and accounting model to come from the requirements rather than from the old code.

---

## 4. What I should understand after rebuilding

I should be able to explain:

- why the contract is payable;
- where the ETH actually lives;
- why `msg.value` is not the same thing as the contract balance;
- how the escrow is identified;
- how the enum/state machine works;
- why caller checks matter;
- why state transitions must be explicit;
- why an ETH transfer should be handled carefully;
- why a successful transfer is not enough by itself;
- how tests prove both valid and invalid behavior.

---

## 5. Minimum test matrix

### Creation

- [ ] valid creation succeeds;
- [ ] ETH arrives at the contract;
- [ ] creator/recipient/amount/status are recorded;
- [ ] invalid participants revert;
- [ ] invalid deposit conditions revert.

### Acceptance

- [ ] recipient can accept;
- [ ] unrelated caller cannot accept;
- [ ] creator cannot impersonate recipient;
- [ ] acceptance changes status exactly once.

### Release

- [ ] creator cannot release before acceptance;
- [ ] recipient cannot release;
- [ ] unrelated caller cannot release;
- [ ] creator can release after acceptance;
- [ ] recipient receives the exact escrow amount;
- [ ] status becomes released;
- [ ] second release reverts.

### Cancellation

- [ ] cancellation follows the chosen rules;
- [ ] released escrow cannot be cancelled;
- [ ] already cancelled escrow cannot be cancelled again;
- [ ] funds return to the intended party.

### Events

- [ ] creation event;
- [ ] acceptance event;
- [ ] release event;
- [ ] cancellation event.

---

## 6. Stretch goals

After the core version works:

- deadline/expiry;
- multiple escrows per user;
- escrow discovery/query helpers;
- dispute resolution;
- reputation/history.

Do these only after the basic state machine is boringly correct.

---

## 7. Rebuild rule

Before opening the old `src/EthEscrow.sol`, create a fresh implementation from this README and the original challenge.

Use the old implementation afterward as a comparison point.

That comparison is the actual learning exercise.
