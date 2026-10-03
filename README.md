# Smart Contract Development Journey

A hands-on archive of my Solidity and smart-contract development journey.

This repository is not meant to be a collection of polished production contracts. It records projects I started while learning Solidity, Foundry, Ethereum concepts, and eventually smart-contract security.

The most useful way to use this repo now is as a **rebuild laboratory**:

> Read the project brief first → close the old implementation → rebuild from memory/spec → test it → compare against the old code only afterward.

That lets the old projects become checkpoints instead of code you simply reread.

---

## Projects

| Project | Original purpose | Current repository state | Main concepts |
| --- | --- | --- | --- |
| [ETH Escrow](ETH%20Escrow/README.md) | Hold ETH between a creator and recipient until the escrow rules are satisfied | Partial implementation; several required rules are missing or incorrectly enforced | payable functions, ETH transfers, state machines, mappings, structs, access control, events, testing |
| [Purchase NFT with ERC20 tokens](Purchase%20NFT%20with%20ERC20%20tokens/README.md) | Explore NFT minting and the idea of purchasing NFTs with ERC20 tokens | NFT minting scaffold exists, but the ERC20 purchase flow was not implemented and tests are empty | ERC20/ERC721 interaction, approve/transferFrom, minting, ownership, token IDs, external contracts |
| [Tipjar](Tipjar%20project/README.md) | Accept ETH tips, track them, and give the owner a withdrawal mechanism | Early/unfinished contract; withdrawal is a stub and the tip accounting is not implemented | payable functions, mappings, modifiers, contract balance, withdrawals, events |

There are currently **three main learning projects** in the repository.

---

# How to Use This Repository Now

The goal of the rebuild pass is not to prove that the old code was bad. The goal is to find out what I can build **without relying on the implementation I already wrote**.

## Recommended workflow

### 1. Pull the repository

```bash
git clone https://github.com/Toji254/Smart-contract-development-journey.git
cd Smart-contract-development-journey
```

Or, if the repository is already cloned:

```bash
git pull
```

Check the Foundry installation:

```bash
forge --version
```

### 2. Pick one project

Start from the project README rather than opening the Solidity file immediately.

For example:

```bash
cd "ETH Escrow"
cat README.md
```

### 3. Rebuild before reading the old implementation

Create a working branch before changing anything:

```bash
git switch -c rebuild/eth-escrow
```

Then rebuild from the specification.

The old implementation is valuable, but it should initially behave like the answer sheet at the back of the textbook: **look only after attempting the problem yourself**.

### 4. Build, test, inspect

Typical Foundry loop:

```bash
forge build
forge test
forge test -vv
forge fmt
```

When something is confusing, reduce it to the smallest experiment possible.

For this journey, a tiny local experiment that proves how Solidity behaves is more valuable than memorising a rule.

### 5. Compare the old implementation afterward

Once the rebuild works, inspect the historical implementation and ask:

- What did I originally get right?
- What did I misunderstand?
- What did I omit?
- What security assumptions did I miss?
- What would fail under an adversarial caller?
- What would I design differently now?

That comparison is part of the exercise.

---

# Rebuild Rules

## Build the behavior, not the old code

Do not copy function bodies from the historical implementation.

The point is to reproduce the **requirements** with a fresh design.

Names, structs, mappings, modifiers, events, IDs, and function signatures can all change unless a project requirement makes them necessary.

## Understand before optimising

At this stage, correctness and understanding matter more than gas micro-optimisation.

A contract you can fully explain is more useful than a clever contract you copied.

## Tests are part of the implementation

For every project, test:

1. expected successful behavior;
2. invalid callers;
3. invalid state transitions;
4. invalid values;
5. repeated actions;
6. edge cases involving zero values, addresses, balances, and external calls.

## Use tools as verification

Foundry, Cast, Anvil, Slither, compiler output, documentation, and AI can all help explain or verify behavior.

The important distinction is:

> **Use tools to improve your understanding, not to replace it.**

---

# Project 1 — ETH Escrow

## What the project is

The escrow is a contract that temporarily holds ETH for an agreement between two parties.

A typical flow is:

```
Creator
   |
   | deposit ETH
   v
Escrow Contract
   |
   | recipient accepts
   v
Accepted
   |
   | creator releases
   v
Recipient receives ETH
```

The original challenge specification is preserved in:

`ETH Escrow/## 🥊 Solidity Weekly Challenge #1 — ETH.md`

That file is the closest thing this project has to a formal original specification.

## What the contract is supposed to do

A complete implementation should support:

### Create an escrow

A creator should be able to create an escrow while depositing ETH.

Each escrow should record enough information to identify and operate on it, including:

- creator;
- recipient;
- amount;
- current status;
- unique identifier.

The implementation is intentionally open-ended.

### Accept an escrow

Only the intended recipient should be able to accept.

Expected state transition:

```
CREATED -> ACCEPTED
```

### Release the payment

Only the creator should be able to release the payment after the recipient has accepted.

Expected state transition:

```
ACCEPTED -> RELEASED
```

The recipient receives the escrowed ETH.

### Cancel an escrow

Cancellation should have explicit rules.

The contract needs to define:

- who can cancel;
- when cancellation is allowed;
- who receives the ETH;
- what state the escrow enters afterward.

### Emit useful events

At minimum:

- creation;
- acceptance;
- release;
- cancellation.

### Provide useful queries

The contract should make it possible to retrieve escrow information and, where appropriate, discover escrows involving an address.

---

## What the historical implementation currently does

The old implementation is useful as a learning artifact, but it should **not** be treated as the completed specification.

Important gaps and problems include:

- escrow storage is hard-coded to key `1` rather than supporting independent escrow IDs;
- the `amount` parameter in `createescrow` does not control the stored escrow amount;
- an unrelated `balances` mapping is updated but has no coherent role in the escrow flow;
- `acceptescrow(false)` attempts to mark the escrow rejected and then reverts, so the state change is rolled back;
- release does not require the escrow to have reached the accepted state;
- release does not update the status to `released`;
- repeated release is not explicitly prevented;
- cancellation is not implemented;
- creation validation is incomplete;
- the repository currently has no meaningful Foundry test suite for the escrow;
- the deployment script is only a starting point.

These are not just bugs to patch. They are clues about what concepts were not yet solid when the project was first written.

---

## What the rebuild should teach

By the end of the rebuild, I should be comfortable with:

- structs inside mappings;
- enums as state machines;
- unique IDs;
- payable functions;
- `msg.value`;
- contract ETH balances;
- checks-effects-interactions;
- low-level ETH transfers;
- access control;
- custom errors or require statements;
- events;
- revert behavior;
- writing positive and negative Foundry tests.

---

## Minimum acceptance tests

The rebuilt version should be able to prove at least:

- a valid escrow can be created;
- the deposited ETH is held by the contract;
- an unrelated account cannot accept another person's escrow;
- the recipient can accept;
- the creator cannot release before acceptance;
- the creator can release after acceptance;
- the recipient receives the correct amount;
- the escrow cannot be released twice;
- invalid escrow creation is rejected;
- cancellation follows the chosen rules;
- invalid state transitions revert.

The exact architecture is mine to decide.

---

# Project 2 — Purchase NFT with ERC20 Tokens

## What the project is

The project name suggests a two-token interaction:

```
Buyer
  |
  | ERC20 payment
  v
Purchase contract
  |
  | mint / transfer NFT
  v
Buyer receives ERC721
```

The repository currently contains an ERC721 contract, but it does **not** yet contain the ERC20 purchase mechanism implied by the project name.

There is also an empty:

`test/PurchaseNFT.t.sol`

which means the testing side of the exercise was not completed.

## What the current code actually does

The current `PurchaseNFT` contract:

- inherits `ERC721URIStorage`;
- creates an NFT collection named `LOKI254` with symbol `LOKI`;
- stores an immutable `OWNER`;
- maintains a token counter;
- exposes a public `mint(address user)` function;
- calls `_safeMint`;
- increments the token counter afterward.

The current implementation does **not**:

- define an ERC20 payment token;
- define a price;
- collect ERC20 payment;
- call `transferFrom`;
- restrict minting to a purchaser/payment flow;
- implement a purchase function;
- implement tests.

There is also a token-ID issue worth investigating during the rebuild: the function mints using the current counter, increments it, and then returns the incremented value rather than the ID that was actually minted.

`OWNER` is also currently stored but not used by the minting logic.

---

## Rebuild target

The original repository does not contain a detailed specification for this project, so the following is an intentionally minimal interpretation derived from the project name and the existing scaffold.

### Core behavior

Build a contract where:

1. an ERC20 token is used as payment;
2. the NFT has a defined purchase price;
3. a buyer approves the purchase contract to spend the required ERC20 amount;
4. the buyer calls a purchase function;
5. the contract pulls the ERC20 payment using `transferFrom`;
6. the buyer receives an NFT;
7. the token ID returned/emitted corresponds to the NFT actually minted;
8. payment reaches the intended owner/seller;
9. invalid payments or purchases revert.

The exact NFT metadata model, supply limits, owner controls, and payment-token setup are design decisions for the rebuild.

---

## What the rebuild should teach

This project should connect two standards instead of treating them as isolated topics.

Focus on:

- ERC20 balances;
- ERC20 allowances;
- `approve`;
- `transferFrom`;
- ERC721 minting;
- token IDs;
- external contract calls;
- ownership/access control;
- payment accounting;
- revert behavior;
- testing interactions between multiple contracts.

The key mental model is:

```
approve()
    |
    v
ERC20 allowance
    |
    v
purchase()
    |
    +--> ERC20.transferFrom(...)
    |
    +--> ERC721 mint
    |
    v
buyer owns NFT
```

---

## Minimum acceptance tests

The rebuilt version should prove:

- a buyer cannot purchase without enough ERC20 balance;
- a buyer cannot purchase without enough allowance;
- a valid approval followed by purchase succeeds;
- the correct ERC20 amount leaves the buyer;
- the intended recipient receives the payment;
- the buyer receives the NFT;
- the NFT token ID is correct;
- repeated purchases behave according to the chosen supply rules;
- unauthorized administrative actions revert;
- failed purchases do not leave partial state behind.

---

# Project 3 — Tipjar

## What the project is

Tipjar is a small ETH-payment contract.

The basic idea is:

```
Any user
   |
   | send ETH tip
   v
Tipjar contract
   |
   +--> record who tipped and how much
   |
   v
Owner can withdraw
```

This is a deliberately small project, which makes it useful for understanding ETH accounting before moving into larger protocols.

---

## What the current code contains

The historical scaffold contains:

- an immutable owner;
- an `onlyowner` modifier;
- a `usertips` mapping;
- a `Tips` event;
- a payable tip function;
- an unfinished withdrawal declaration.

The implementation is incomplete.

In particular:

- tips are not actually added to `usertips`;
- the local `tip` parameter does not provide persistent accounting;
- the existing increment expression involving `msg.value` is not a valid way to mutate the transaction value;
- the withdrawal function is unfinished/malformed;
- there are no meaningful tests.

This project should therefore be treated as a **rebuild exercise**, not as a bug-fixing exercise.

---

## Rebuild target

Build a simple ETH tip jar with these rules.

### Tipping

Anyone can call a payable tip function.

The contract should:

- require a meaningful tip amount;
- increase the sender's cumulative tip total;
- retain the ETH in the contract;
- emit an event containing useful information.

### Withdrawal

Only the owner can withdraw.

The owner should be able to specify:

- how much ETH to withdraw;
- which recipient should receive it.

The contract should reject:

- non-owner withdrawals;
- withdrawals larger than the available balance;
- invalid recipients according to the chosen design;
- other impossible states you identify.

### Accounting

The rebuilt contract should make it possible to answer:

> How much has this address tipped through the contract?

That is what the `usertips` mapping appears intended to represent.

The important distinction is:

```
usertips[user]
    =
historical amount tipped by user
```

versus:

```
address(this).balance
    =
ETH currently held by the contract
```

Those are related, but they are **not the same thing**.

---

## What the rebuild should teach

Focus on:

- payable functions;
- `msg.value`;
- `address(this).balance`;
- mappings;
- state updates;
- owner-only functions;
- ETH withdrawal;
- external calls;
- events;
- accounting invariants.

A useful invariant to think about is:

> Recording a tip in storage should never be confused with the contract's current ETH balance.

---

## Minimum acceptance tests

### Tipping

- [ ] a user can send a tip;
- [ ] the user's cumulative tip amount increases correctly;
- [ ] the contract balance increases correctly;
- [ ] the tip event is emitted;
- [ ] repeated tips accumulate correctly.

### Withdrawal

- [ ] a non-owner cannot withdraw;
- [ ] the owner can withdraw a valid amount;
- [ ] the recipient receives the correct amount;
- [ ] an over-withdrawal reverts;
- [ ] a failed withdrawal does not corrupt accounting;
- [ ] multiple withdrawals behave correctly.

---

# Suggested Rebuild Order

The projects are small enough to rebuild in increasing complexity.

## 1. Tipjar

Start here to reinforce:

```
msg.value
      |
      v
state update
      |
      v
contract balance
      |
      v
owner withdrawal
```

This is a good warm-up for ETH accounting.

## 2. ETH Escrow

Then move to a state machine:

```
CREATED -> ACCEPTED -> RELEASED
       \\-> CANCELLED
```

This adds multiple actors, authorization, state transitions, and a larger test matrix.

## 3. Purchase NFT with ERC20 Tokens

Finish with multiple contracts interacting:

```
ERC20
  |
  | allowance / transferFrom
  v
Purchase contract
  |
  | mint
  v
ERC721
```

That gives the rebuild sequence a natural progression from **single-contract ETH accounting → multi-party state machine → cross-contract token interaction**.

---

# Rebuild Checklist

Use this whenever starting one of the projects.

### Before coding

- [ ] Read the project README completely.
- [ ] Identify actors.
- [ ] Identify stored state.
- [ ] Identify assets that can move.
- [ ] Identify valid state transitions.
- [ ] Identify who is allowed to call each operation.
- [ ] Write down failure cases.
- [ ] Decide what events are useful.
- [ ] Write down the minimum tests before implementation.

### During coding

- [ ] Keep the implementation understandable.
- [ ] Compile frequently.
- [ ] Run tests after small changes.
- [ ] Use local Anvil experiments for confusing behavior.
- [ ] Do not silently weaken requirements just to make tests pass.

### After coding

- [ ] Run the full Foundry test suite.
- [ ] Inspect the contract manually.
- [ ] Compare implementation against the specification.
- [ ] Inspect the historical implementation.
- [ ] Record what was previously misunderstood.
- [ ] Look for security implications and broken invariants.
- [ ] Keep notes on anything that required documentation/research.

---

# The Actual Goal of This Repository

This repository is most useful when it shows **the evolution of understanding**, not just a pile of finished Solidity files.

A successful rebuild means I can explain:

- what the contract is supposed to do;
- what every important state variable represents;
- who can change that state;
- how ETH/tokens move;
- which assumptions the contract makes;
- what happens when those assumptions fail;
- why the tests prove the intended behavior;
- and where an attacker might look for an unexpected state transition.

The old code is evidence of where the journey started.

The rebuilt code is evidence of what I understand now.

---

## Useful Commands

From inside any project:

```bash
forge build
forge test
forge test -vv
forge fmt
```

Start a local EVM when you want to interact manually:

```bash
anvil
```

Use Cast for contract/chain interaction:

```bash
cast --help
```

For security-oriented follow-up, the next layer after the rebuild is to run static analysis, inspect storage/layout where relevant, and deliberately attack the assumptions you wrote down before looking at any outside solution.

---

## Repository Philosophy

**Build. Break. Explain. Rebuild.**

The objective is not to remember what was written in these folders.

The objective is to reach the point where, given a plain-English smart-contract requirement, I can design the state model, implement it, test it, interact with it, and then start looking for ways it can fail.
