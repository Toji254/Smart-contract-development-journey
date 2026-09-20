## 🥊 Solidity Weekly Challenge #1 — ETH Escrow

**Difficulty:** Beginner → Early Intermediate
**Duration:** 5–7 days
**AI:** ❌ No AI-generated code
**Research:** ✅ Allowed
**Format:** Both participants build independently, then compare implementations afterward.

### 🎯 The Project

Build a decentralized **ETH Escrow** smart contract.

The idea is simple:

A user wants to pay another user for something, but instead of sending the ETH directly, the money is held by the smart contract until the agreed conditions are met.

Basic flow:

**Creator → deposits ETH → Escrow Contract → Recipient accepts → Creator releases → Recipient receives ETH**

The contract should enforce the rules so that neither party can simply take control of the funds.

---

### 📋 Core Requirements

#### 1. Create an Escrow

A user should be able to create an escrow agreement while depositing ETH.

The escrow should keep track of relevant information such as:

* Creator
* Recipient
* Amount
* Current status
* A unique identifier

The exact data structures are up to each participant.

---

#### 2. Accept the Escrow

Only the intended recipient should be able to accept an escrow.

The escrow should move from something like:

`CREATED → ACCEPTED`

The exact implementation is up to you.

---

#### 3. Release the Payment

The creator should be able to release the ETH **only after the recipient has accepted**.

After release:

`ACCEPTED → RELEASED`

The recipient should receive the escrowed ETH.

---

#### 4. Cancel an Escrow

There should be a way to cancel an escrow.

You must determine:

* Who can cancel it
* When cancellation is allowed
* Who receives the ETH after cancellation

The rules should make sense and be enforced by the contract.

---

### 🚨 Things the Contract Should Prevent

The contract should handle invalid actions such as:

* A random address accepting someone else's escrow
* The recipient releasing their own payment
* The creator releasing before acceptance
* Releasing an escrow twice
* Cancelling an already released escrow
* Cancelling an already cancelled escrow
* Creating an escrow with invalid participants
* Incorrect ETH amounts
* Other invalid state transitions you identify during development

---

### 📢 Events

The contract should emit events for important actions.

At minimum, consider events for:

* Escrow creation
* Escrow acceptance
* Escrow release
* Escrow cancellation

The information stored in each event is up to you.

---

### 📊 Querying

The contract should provide a way to retrieve escrow information.

For example:

* Get a specific escrow
* Find existing escrows
* Find escrows created by an address
* Find escrows involving an address

How this is implemented is part of the challenge.

---

### 🧪 Foundry Tests

The project should include Foundry tests.

Tests should cover both:

**Successful behavior**

and

**Invalid behavior that should revert.**

Examples:

* Can the recipient accept?
* Can an unrelated address accept?
* Can the creator release before acceptance?
* Can the creator release after acceptance?
* Does the recipient receive the ETH?
* Can an escrow be released twice?
* Can an invalid escrow be created?
* Does cancellation behave correctly?

The exact test suite is up to each participant.

---

## ⭐ Optional Stretch Goals

Only attempt these after completing the core requirements.

### Deadline

Allow an escrow to expire after a certain amount of time.

### Dispute System

Introduce a third party that can resolve disputes.

### Reputation

Track successful escrows associated with each address.

### Multiple Escrows

Allow users to create and retrieve multiple escrows easily.

---

# 🥊 Competition Rules

### 1. Build independently

Both participants receive the same requirements but design and implement their own solutions.

### 2. No AI-generated code

No asking AI to write the contract, functions, tests, or implementation for you.

### 3. Research is allowed

Solidity documentation, Foundry documentation, Cyfrin, Stack Overflow, GitHub, tutorials, articles, etc. are all fair game.

### 4. Don't copy an existing implementation

Research concepts freely, but the final implementation should be your own.

### 5. Don't exchange code before the deadline

Discussion of concepts is fine, but implementations remain private until the comparison.

---

# 🏆 Final Comparison

After the deadline, both implementations can be compared based on:

| Category               |  Weight |
| ---------------------- | ------: |
| Correctness            |      30 |
| Security               |      25 |
| Architecture           |      15 |
| Solidity Understanding |      10 |
| Testing                |      10 |
| Code Quality           |       5 |
| Useful Extras          |       5 |
| **Total**              | **100** |

The goal isn't simply to produce the shortest contract.

The goal is to build something that is **correct, secure, understandable, and properly tested.**

Good luck. ⚔️
