# BountyArena

## Project Overview

**BountyArena** is a small on-chain bounty platform.

A user creates a bounty by depositing ETH into the smart contract and assigning a hunter to complete the task. The hunter claims the bounty, submits a solution, and waits for the bounty creator to approve it.

When the creator approves the solution, the hunter earns the bounty. The hunter does not receive the ETH immediately; instead, the ETH is added to their withdrawable balance.

The contract also includes a simple reputation system, allowing only hunters with enough reputation to claim bounties.

The project is intentionally small, but several Solidity concepts must be combined together rather than used independently.

---

# 1. Main Participants

There are three important participants.

### Contract Owner

The address that deploys the contract.

The owner is responsible for:

* controlling owner-only functionality
* resolving disputed bounties
* interacting with the reputation system where necessary

Use OpenZeppelin's `Ownable` for ownership.

---

### Bounty Creator

The person who creates a bounty.

A creator:

1. Creates a bounty.
2. Deposits ETH with the bounty.
3. Specifies the hunter who is expected to complete it.
4. Reviews the submitted solution.
5. Approves the solution.
6. Can cancel an open bounty.

---

### Hunter

The person assigned to complete a bounty.

A hunter:

1. Attempts to claim a bounty.
2. Must satisfy the reputation requirement.
3. Submits a solution.
4. Receives the bounty when the creator approves the solution.
5. Withdraws their earned ETH.

A user can be both a creator and a hunter in different bounties.

---

# 2. Bounty Lifecycle

Every bounty follows a simple state machine.

```text
Open
  ↓
Claimed
  ↓
Submitted
  ↓
Completed
```

There is also a cancellation path:

```text
Open
  ↓
Cancelled
```

And a dispute path:

```text
Claimed / Submitted
       ↓
    Disputed
       ↓
    Resolved
       ↓
   Completed
```

You must decide the exact rules for which states can move into `Disputed`.

---

# 3. Bounty Data Structure

Create a `Bounty` struct.

It should contain the main information about a bounty.

At minimum, include:

* bounty creator
* hunter
* amount of ETH
* title or description
* submitted solution hash
* current status

### Required combination: Struct + Array

Each bounty must also contain a small array of tags.

For example:

```text
Solidity
DeFi
Audit
Bug
```

Do **not** store these as one giant string.

Use an array inside the struct.

Use a suitable type such as `bytes32[]`.

Conceptually:

```text
Bounty
├── creator
├── hunter
├── amount
├── description
├── solutionHash
├── status
└── tags[]
```

This is deliberate: you must practice working with an **array inside a struct**.

The tags should be supplied when the bounty is created.

---

# 4. Bounty Storage

Store every bounty using its `bytes32` ID.

Conceptually:

```text
bytes32 ID
     ↓
Bounty struct
     ↓
creator
hunter
amount
status
tags[]
...
```

This gives you:

**mapping → struct → array**

You should be comfortable navigating something conceptually like:

```text
bounties[id].tags
```

without treating the pieces as separate concepts.

---

# 5. Creator Bounty History

Maintain another data structure that records which bounties each creator has created.

### Required combination: Mapping + Array

Use a structure equivalent to:

```text
address → bytes32[]
```

Meaning:

```text
Creator address
      ↓
[ Bounty ID 1, Bounty ID 2, Bounty ID 3 ]
```

Whenever someone creates a bounty:

1. Create the bounty ID.
2. Store the bounty in the main mapping.
3. Add the ID to the creator's bounty array.

This gives you practice with:

**mapping → dynamic array**

Do not replace this with one global array.

You need both:

```text
allBountyIds
```

and:

```text
creatorBountyIds[creator]
```

---

# 6. Hunter History

You may also maintain a second history structure for hunters.

For example:

```text
address → bytes32[]
```

containing bounties a hunter has claimed or completed.

This is optional, but recommended because it makes you work with nested data structures more.

Do not over-engineer this.

---

# 7. Bounty IDs

Every bounty must have a `bytes32` ID.

The ID should be generated using `keccak256` from useful information about the bounty.

Do not simply use:

```text
1
2
3
4
```

Your ID-generation design should make collisions extremely unlikely.

You should be able to explain why the values being hashed are sufficient for your design.

---

# 8. Creating a Bounty

A creator starts by calling the bounty creation function.

The creator must send ETH with the transaction.

Example:

```text
Creator
   │
   │ create bounty + ETH
   ▼
BountyArena
```

When the bounty is created:

1. Verify that the deposited amount is greater than zero.
2. Generate a unique `bytes32` bounty ID.
3. Generate it using `keccak256`.
4. Store the bounty in the main mapping.
5. Store the supplied tags inside the bounty's `tags[]` array.
6. Add the bounty ID to the global bounty ID array.
7. Add the bounty ID to the creator's personal bounty array.
8. Emit a `BountyCreated` event.

The bounty begins in:

```text
Open
```

This single function should therefore combine:

```text
payable function
       ↓
msg.sender
       ↓
msg.value
       ↓
keccak256
       ↓
bytes32
       ↓
struct
       ↓
array inside struct
       ↓
mapping
       ↓
mapping(address => bytes32[])
       ↓
global array
       ↓
event
```

That combination is intentional.

---

# 9. Reputation System

BountyArena interacts with an external reputation contract through an interface.

The purpose is simple:

> A hunter must have a minimum reputation before claiming a bounty.

BountyArena does not implement the reputation system itself.

Instead:

```text
BountyArena
     │
     │ interface call
     ▼
Reputation Contract
```

Create an interface exposing a function that returns a user's reputation.

For testing, create a small mock reputation contract.

The main contract should store the reputation contract's address.

---

# 10. Claiming a Bounty

Once a bounty exists, the assigned hunter can claim it.

The hunter must satisfy all required conditions.

At minimum:

1. The bounty must exist.
2. The bounty must currently be `Open`.
3. The caller must be the assigned hunter.
4. The hunter must not be the bounty creator.
5. The hunter must have enough reputation.

When successful:

```text
Open → Claimed
```

Store the hunter where appropriate.

Also update the hunter's bounty history if you implemented it.

Emit:

```text
BountyClaimed
```

This gives you another combination:

```text
mapping
    ↓
struct
    ↓
enum state
    ↓
interface call
    ↓
msg.sender
```

---

# 11. Submitting a Solution

After claiming a bounty, the hunter can submit a solution.

Do not store the full solution on-chain.

Instead, store a `bytes32` hash.

The hunter submits information that can be hashed.

The contract:

1. Verifies the bounty exists.
2. Verifies the caller is the hunter.
3. Verifies the bounty is in the correct state.
4. Creates the solution hash using `keccak256`.
5. Stores the resulting hash in the bounty.
6. Changes the bounty status.

State transition:

```text
Claimed → Submitted
```

Emit:

```text
SolutionSubmitted
```

You must decide whether to use:

```solidity
abi.encode(...)
```

or:

```solidity
abi.encodePacked(...)
```

and be able to explain your decision afterward.

---

# 12. Approving the Solution

The bounty creator reviews the submitted work.

Only the creator of that bounty can approve it.

Before approval:

* the bounty must exist
* caller must be the creator
* bounty must be in the correct state
* a solution must have been submitted

When approved:

```text
Submitted → Completed
```

The hunter does not receive ETH directly.

Instead, the bounty amount is added to their withdrawable balance.

Conceptually:

```text
hunterBalances[hunter]
        +
     bounty.amount
```

Emit:

```text
BountyCompleted
```

---

# 13. Hunter Withdrawals

Hunters can withdraw their earned ETH.

Maintain a balance mapping equivalent to:

```text
address → uint256
```

When a hunter withdraws:

1. Check that their balance is greater than zero.
2. Store the amount to withdraw.
3. Set their stored balance to zero.
4. Perform the external ETH transfer.
5. Verify that the transfer succeeded.
6. Emit a withdrawal event.

Use low-level:

```solidity
call
```

for the ETH transfer.

Clear the balance before the external call.

This gives you practice with:

```text
mapping
   ↓
value retrieval
   ↓
state update
   ↓
external call
```

---

# 14. Cancelling a Bounty

A creator can cancel a bounty while it is in an allowed state.

At minimum, an `Open` bounty should be cancellable.

When cancelled:

```text
Open → Cancelled
```

The bounty's ETH should become withdrawable by the creator.

Do not immediately send ETH from the cancellation function.

Instead, credit the creator's withdrawable balance.

Emit:

```text
BountyCancelled
```

Think carefully about whether the bounty amount can accidentally be credited more than once.

---

# 15. Disputes

A dispute allows a bounty to be escalated when the parties disagree.

A valid dispute changes the bounty to:

```text
Disputed
```

Only the participants you consider appropriate should be able to open a dispute.

The owner resolves the dispute.

The owner chooses whether the bounty goes to:

```text
Creator
```

or:

```text
Hunter
```

The chosen party receives an amount in their withdrawable balance.

The bounty becomes completed/resolved according to your design.

Emit:

```text
BountyResolved
```

Your implementation must prevent a dispute from being resolved more than once.

---

# 16. Owner and Inheritance

Use OpenZeppelin's `Ownable`.

Do not write your own owner variable and `onlyOwner` implementation.

Your contract should inherit from the OpenZeppelin ownership contract.

Conceptually:

```text
OpenZeppelin Ownable
        ↓
   BountyArena
```

Use ownership for administrative actions such as dispute resolution.

This gives you practice with:

```text
import
   ↓
inheritance
   ↓
inherited modifier
   ↓
owner-controlled function
```

---

# 17. Constructor

The constructor should initialize the inherited ownership system and the reputation contract address.

Think about why the reputation contract address should be supplied when deploying instead of hardcoded into your contract.

---

# 18. Direct ETH Transfers

Implement both:

```text
receive()
fallback()
```

Decide what should happen when ETH is sent directly to the contract without creating a bounty.

Your accounting system should not accidentally treat random ETH as belonging to a particular bounty.

After implementing this, you should understand the difference between:

```text
ETH physically held by the contract
```

and:

```text
ETH accounted for in individual balances
```

---

# 19. Internal Function

Create at least one meaningful `internal` function.

For example, you may have reusable internal logic for crediting a user's balance after a bounty outcome.

Do not create an internal function simply to satisfy the requirement.

---

# 20. Events

Emit events whenever important state changes happen.

At minimum:

```text
BountyCreated
BountyClaimed
SolutionSubmitted
BountyCompleted
BountyCancelled
BountyDisputed
BountyResolved
Withdrawal
```

Use `indexed` parameters where appropriate.

---

# 21. Custom Errors

Use custom errors for important failure conditions.

The contract should clearly reject situations such as:

* zero-value bounty
* nonexistent bounty
* invalid status
* unauthorized caller
* insufficient reputation
* invalid hunter
* no withdrawal balance
* failed ETH transfer

Choose your own error names and parameters.

---

# 22. Required Data Structures

Your implementation should contain all of these:

### Main bounty mapping

```text
bytes32 → Bounty
```

### Balance mapping

```text
address → uint256
```

### Creator history mapping

```text
address → bytes32[]
```

### Global bounty array

```text
bytes32[]
```

### Array inside the Bounty struct

```text
bytes32[] tags
```

So your data model should contain these relationships:

```text
mapping
   ↓
Bounty struct
   ↓
tags array
```

and:

```text
mapping(address => bytes32[])
          ↓
    creator's bounties
```

and:

```text
global array
      ↓
all bounty IDs
```

This is one of the main learning objectives of the project.

---

# 23. Required Solidity Features

The finished project should demonstrate:

* structs
* mappings
* nested mappings/arrays where appropriate
* arrays
* arrays inside structs
* enum
* events
* modifiers
* custom errors
* constructors
* immutable variables where appropriate
* payable functions
* `msg.sender`
* `msg.value`
* `address(this)`
* `address(this).balance`
* `keccak256`
* `abi.encode` or `abi.encodePacked`
* internal functions
* interfaces
* imports
* inheritance
* external contract calls
* `receive`
* `fallback`
* low-level `call`

---

# 24. Example User Flow

## Successful bounty

```text
1. Deploy MockReputation.

2. Give Hunter enough reputation.

3. Deploy BountyArena with the reputation contract address.

4. Creator creates a bounty and deposits ETH.

5. Creator supplies several tags.

6. Contract creates a bytes32 bounty ID.

7. ID is stored in the main bounty mapping.

8. ID is added to the global bounty array.

9. ID is added to the creator's personal bounty array.

10. Hunter claims the bounty.

11. Hunter submits a solution.

12. Creator approves the solution.

13. Hunter's withdrawable balance increases.

14. Hunter withdraws the ETH.
```

---

# 25. Example Cancellation Flow

```text
1. Creator creates bounty.

2. Bounty remains Open.

3. Creator cancels it.

4. Bounty becomes Cancelled.

5. Creator's withdrawable balance increases.

6. Creator withdraws the ETH.
```

---

# 26. Example Dispute Flow

```text
1. Creator creates bounty.

2. Hunter claims bounty.

3. A valid participant opens a dispute.

4. Bounty becomes Disputed.

5. Owner resolves the dispute.

6. Owner chooses Creator or Hunter.

7. Chosen party receives a withdrawable balance.

8. Chosen party withdraws the ETH.
```

---

# 27. What the Contract Must Prevent

The contract should reject situations such as:

```text
A random user claiming someone else's bounty.

A hunter with insufficient reputation claiming a bounty.

A hunter submitting before claiming.

A creator approving before a submission exists.

A creator cancelling a completed bounty.

A bounty being completed twice.

A bounty being cancelled twice.

A hunter withdrawing the same balance twice.

A dispute being resolved twice.

A non-owner resolving a dispute.

A user withdrawing with a zero balance.

A bounty's funds being credited twice.

A bounty being given to the wrong user.

Invalid state transitions.

Creating a bounty with zero ETH.

Sending more ETH than the contract can actually pay.
```

---

# 28. Foundry Tests

Write tests for the main system behavior.

At minimum test:

### Creation

* bounty is created
* amount is correct
* creator is correct
* tags are stored
* ID is generated
* ID is added to the global array
* ID is added to the creator's array
* event is emitted

### Claiming

* correct hunter can claim
* wrong user cannot claim
* insufficient reputation cannot claim
* bounty cannot be claimed twice
* creator cannot claim their own bounty

### Submission

* hunter can submit
* non-hunter cannot submit
* submission cannot happen in the wrong state
* solution hash is stored

### Completion

* creator can approve
* non-creator cannot approve
* correct hunter receives the balance
* bounty cannot be completed twice

### Cancellation

* creator can cancel when allowed
* unauthorized user cannot cancel
* correct user receives the balance
* cancelled bounty cannot be processed again

### Withdrawal

* user can withdraw
* balance becomes zero
* correct ETH amount is sent
* withdrawal event is emitted
* failed transfer is handled

### Disputes

* valid participant can dispute
* invalid participant cannot dispute
* only owner can resolve
* correct party receives funds
* dispute cannot be resolved twice

### Reputation

* insufficient reputation blocks claiming
* sufficient reputation allows claiming

---

# 29. Final Architecture Goal

Your final contract should roughly have this conceptual structure:

```text
                    BountyArena
                         │
          ┌──────────────┼──────────────┐
          │              │              │
       Ownable      Reputation       Bounty Data
          │           Interface          │
          │                              │
      onlyOwner                    bytes32 → Bounty
                                         │
                           ┌─────────────┼─────────────┐
                           │             │             │
                        creator       hunter        tags[]
                        amount        status
                        solutionHash
```

And separately:

```text
creator address
      ↓
bytes32[]
      ↓
creator's bounty IDs
```

and:

```text
user address
      ↓
uint256
      ↓
withdrawable ETH
```

and:

```text
bytes32[]
      ↓
all bounty IDs
```

The important part is that these structures must **work together**.

You shouldn't finish the project thinking:

> "I used a mapping. I used an array. I used a struct."

You should be thinking:

> "My mapping stores structs, those structs contain arrays, another mapping stores arrays of IDs, and those IDs point back to the structs."

That is the skill this project is testing.

---

# 30. Timebox

### 0–5 minutes

Design the architecture.

### 5–40 minutes

Write the contract.

### 40–55 minutes

Write Foundry tests.

### 55–60 minutes

Try to break it.

Test things like:

```text
claim twice
submit too early
complete twice
cancel after completion
dispute invalid bounty
resolve twice
withdraw twice
wrong caller
zero ETH
bad reputation
fake bounty ID
```

---

# Final Objective

Build BountyArena so that someone can:

> Create a funded bounty → assign/claim a hunter → verify reputation → store tags → submit a hashed solution → approve or dispute the bounty → account for the ETH → withdraw the funds.

The project should be small enough to finish in about an hour, but interconnected enough that you have to actively think about:

```text
structs
   +
mappings
   +
arrays
   +
enums
   +
modifiers
   +
events
   +
errors
   +
hashing
   +
interfaces
   +
inheritance
   +
ETH accounting
   +
external calls
   +
state machines
```

**Do not copy the implementation from another project. Design it from this specification and write it yourself.**
