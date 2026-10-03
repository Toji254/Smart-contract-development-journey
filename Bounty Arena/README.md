# BountyArena

## What you are building

BountyArena is the integration project in this repository.

~~~text
Creator
  │
  │ create bounty + ETH
  ▼
BountyArena
  │
  │ hunter claims
  ▼
Hunter
  │
  │ submits solution
  ▼
Creator reviews
  │
  ├── approve ─────→ Hunter earns ETH
  │
  └── dispute ─────→ Owner resolves
~~~

The goal is to build this system from the requirements below, not from the existing implementation.

## 0. Learning objective

By the end, these should feel like one connected model:

~~~text
mapping
   ↓
struct
   ↓
array inside struct
   ↓
bytes32 ID
   ↓
address → bytes32[]
   ↓
enum state
   ↓
ETH accounting
   ↓
external contract call
   ↓
withdrawal
~~~

The point is not to collect Solidity keywords. The point is to understand how the pieces interact.

## 1. Define the actors

### Creator

Creates and funds a bounty, reviews work, approves eligible work, cancels an eligible bounty, and may participate in disputes according to your rules.

### Hunter

Claims the bounty, submits a solution, earns a credited balance, and withdraws ETH.

### Contract owner

Handles administrative actions such as dispute resolution. Use OpenZeppelin ownership rather than inventing a parallel owner system.

A single address may play different roles in different bounties.

## 2. Draw the state machine first

Core path:

~~~text
OPEN
  ↓
CLAIMED
  ↓
SUBMITTED
  ↓
COMPLETED
~~~

Cancellation:

~~~text
OPEN → CANCELLED
~~~

Dispute:

~~~text
CLAIMED / SUBMITTED
        ↓
     DISPUTED
        ↓
      owner
        ↓
     RESOLVED
~~~

Do not let a function change state just because the caller is authorized. The current state must also be valid.

## 3. Design the Bounty struct

At minimum, a bounty needs to remember:

- creator;
- hunter;
- amount of ETH;
- description;
- submitted solution hash;
- status;
- tags.

Conceptually:

~~~text
Bounty
├── creator
├── hunter
├── amount
├── description
├── solutionHash
├── status
└── tags[]
~~~

## 4. Put tags inside the struct

Use a small array, such as a bytes32 array.

Example:

~~~text
Solidity
DeFi
Audit
~~~

This is deliberate practice for:

~~~text
mapping → struct → array
~~~

## 5. Store bounties in a mapping

Every bounty needs an identifier.

Use a bytes32 ID and map it to the Bounty struct:

~~~text
bytes32 → Bounty
~~~

Ask:

> What does bounties[id] mean, and what does bounties[id].tags mean?

Do not treat the mapping, struct, and array as unrelated features.

## 6. Track creator history

Add a relationship of the form:

~~~text
address → bytes32[]
~~~

This lets you answer which bounties a creator created.

Whenever a bounty is created:

1. create the ID;
2. store the bounty;
3. add the ID to the global list;
4. add the ID to the creator's list.

## 7. Track all bounty IDs

Keep a global bytes32 array.

You now have:

~~~text
bytes32[] allBountyIds
address → bytes32[] creatorBountyIds
bytes32 → Bounty bounties
~~~

These are different views of the same underlying data.

## 8. Optional hunter history

After creator history works, you may add an address to bytes32 array for hunter history.

Do not over-engineer this first.

## 9. Generate bounty IDs

Use keccak256 rather than a simple visible counter.

The learning chain is:

~~~text
inputs
   ↓
ABI encoding
   ↓
keccak256
   ↓
bytes32 bounty ID
~~~

You should be able to explain why the hashed values are sufficient to distinguish bounties for your design.

## 10. Understand ABI encoding

Before choosing between abi.encode and abi.encodePacked, understand how they represent the inputs and why packed representations can create ambiguity for some dynamic values.

The target is understanding the bytes being hashed, not memorising a preferred spelling.

## 11. Create a bounty

The creator sends ETH with the creation transaction.

Conceptual flow:

~~~text
Creator
  ↓
validate
  ↓
msg.sender + msg.value
  ↓
generate bytes32 ID
  ↓
build Bounty
  ↓
store mapping entry
  ↓
copy tags
  ↓
append global ID
  ↓
append creator ID
  ↓
emit BountyCreated
~~~

The initial state is OPEN.

## 12. Validate bounty creation

Choose and document rules for zero ETH, zero-address hunter, creator equal to hunter, empty description, and empty tags.

Not every field must be rejected. The important part is that your rules are intentional and tested.

## 13. Build the reputation interface

BountyArena should query an external reputation contract instead of implementing the reputation system itself.

~~~text
BountyArena
    │
    │ interface call
    ▼
Reputation contract
~~~

Create a small mock reputation contract for Foundry tests.

Pass the reputation contract address into the BountyArena constructor instead of hardcoding one deployment.

## 14. Claim a bounty

Valid transition:

~~~text
OPEN → CLAIMED
~~~

At minimum:

1. bounty exists;
2. state is OPEN;
3. caller is the assigned hunter;
4. hunter is not the creator;
5. reputation is high enough.

The reputation query is your first important cross-contract check.

## 15. Test claiming

Cover:

- correct hunter with enough reputation;
- wrong caller;
- creator trying to claim;
- low reputation;
- unknown bounty ID;
- repeated claim;
- wrong state.

## 16. Submit a solution

Do not store the full solution on-chain.

Store a bytes32 solution hash.

Flow:

~~~text
verify hunter
   ↓
verify CLAIMED
   ↓
hash submission data
   ↓
store solutionHash
   ↓
CLAIMED → SUBMITTED
~~~

Think carefully about what exactly is included in the hash.

## 17. Test submission

Prove the hunter can submit, a non-hunter cannot, submission before claiming fails, wrong-state submission fails, and the hash is stored correctly.

Decide whether resubmission is allowed. Encode that decision in the state machine and tests.

## 18. Approve a bounty

Only the creator may approve a submitted bounty.

Before approval:

~~~text
bounty exists
caller == creator
status == SUBMITTED
~~~

Then:

~~~text
SUBMITTED → COMPLETED
~~~

Do not immediately push ETH to the hunter in the core design. Credit a withdrawable balance instead.

## 19. Build withdrawable ETH accounting

Use:

~~~text
address → uint256
~~~

This is entitlement accounting, not separate physical piles of ETH.

Physical ETH is held by:

~~~text
address(this).balance
~~~

That distinction is central to the project.

## 20. Withdraw safely

Conceptual order:

~~~text
check balance
   ↓
read amount
   ↓
set stored balance to zero
   ↓
external ETH transfer
   ↓
verify success
   ↓
emit event
~~~

Clearing the balance before the external call is deliberate.

Ask what a contract recipient could do during the transfer.

## 21. Test withdrawal

Cover:

- user can withdraw;
- stored balance becomes zero;
- recipient receives the correct amount;
- second withdrawal cannot repeat the payout;
- zero balance fails;
- failed transfer is handled.

## 22. Cancellation

Basic path:

~~~text
OPEN → CANCELLED
~~~

Only the creator can use the basic cancellation path.

Credit the creator's withdrawable balance rather than immediately pushing ETH.

Test that the same bounty cannot be credited twice.

## 23. Disputes

Only after the core create → claim → submit → complete flow is correct.

Possible path:

~~~text
CLAIMED / SUBMITTED
        ↓
DISPUTED
        ↓
RESOLVED
~~~

You must explicitly define:

- who may open a dispute;
- which states can be disputed;
- who may resolve;
- how the winner is chosen;
- what happens to the bounty funds;
- how double resolution is prevented.

## 24. Ownership and inheritance

Use OpenZeppelin Ownable.

The learning chain is:

~~~text
import
  ↓
inheritance
  ↓
inherited owner state
  ↓
onlyOwner
  ↓
admin action
~~~

Understand what the inherited contract provides instead of treating onlyOwner as magic.

## 25. Constructor dependencies

Initialize ownership and store the reputation contract address.

Ask which addresses belong in deployment configuration instead of being permanently hardcoded.

## 26. receive() and fallback()

Only after normal bounty creation is working, decide what direct ETH transfers should do.

An unsolicited transfer is not automatically a bounty.

Your accounting must distinguish:

~~~text
ETH physically held
        ≠
ETH already attributed to a specific bounty liability
~~~

## 27. Meaningful internal helper

Create at least one useful internal function, such as shared balance-crediting logic.

Do not create a helper only to tick a Solidity feature box.

## 28. Events

Think about events for:

- BountyCreated;
- BountyClaimed;
- SolutionSubmitted;
- BountyCompleted;
- BountyCancelled;
- BountyDisputed;
- BountyResolved;
- Withdrawal.

Choose indexed fields where they make sense.

## 29. Custom errors

Use custom errors for important failure conditions such as unknown bounty, invalid state, unauthorized caller, insufficient reputation, zero withdrawal balance, failed ETH transfer, or invalid resolution.

Choose names and parameters that communicate the failure.

## 30. Minimum complete data model

~~~text
bytes32 → Bounty
address → uint256
address → bytes32[]
bytes32[]
Bounty.tags → bytes32[]
~~~

Read this as one connected model, not a checklist.

## 31. Minimum success flow

~~~text
1. Deploy MockReputation.
2. Give hunter enough reputation.
3. Deploy BountyArena with reputation address.
4. Creator creates funded bounty.
5. Tags are stored.
6. Bounty receives bytes32 ID.
7. ID enters main mapping.
8. ID enters global array.
9. ID enters creator history.
10. Hunter claims.
11. Reputation is checked.
12. Hunter submits solution.
13. Creator approves.
14. Hunter balance is credited.
15. Hunter withdraws.
~~~

Do this before adding disputes or other advanced features.

## 32. Cancellation flow

~~~text
Creator creates
      ↓
OPEN
      ↓
Creator cancels
      ↓
CANCELLED
      ↓
Creator withdrawable credit
      ↓
Creator withdraws
~~~

Prove the credit cannot happen twice.

## 33. Dispute flow

~~~text
create
  ↓
claim
  ↓
submit
  ↓
dispute
  ↓
owner resolves
  ↓
winner gets credit
  ↓
winner withdraws
~~~

## 34. Foundry test plan

Write tests as you build, not only at the end.

### Creation

- [ ] bounty exists;
- [ ] creator, hunter, amount are correct;
- [ ] tags are stored;
- [ ] ID is generated;
- [ ] ID is stored globally and for the creator;
- [ ] event is emitted.

### Claiming

- [ ] correct hunter can claim;
- [ ] wrong user cannot;
- [ ] creator cannot claim own bounty;
- [ ] low reputation fails;
- [ ] double claim fails.

### Submission

- [ ] hunter can submit;
- [ ] non-hunter cannot;
- [ ] wrong state fails;
- [ ] solution hash is stored.

### Completion

- [ ] creator can approve;
- [ ] non-creator cannot;
- [ ] hunter gets exactly one correct credit;
- [ ] completion cannot happen twice.

### Cancellation

- [ ] creator can cancel when allowed;
- [ ] unauthorized caller fails;
- [ ] terminal bounty cannot cancel;
- [ ] creator gets exactly one credit.

### Withdrawal

- [ ] balance is paid correctly;
- [ ] balance becomes zero;
- [ ] second withdrawal fails;
- [ ] failed transfer is handled.

### Disputes

- [ ] valid participant can dispute;
- [ ] invalid participant cannot;
- [ ] only owner resolves;
- [ ] correct party gets credit;
- [ ] resolution cannot happen twice.

## 35. Manual Anvil walkthrough

Use at least these local actors:

~~~text
owner
creator
hunter
attacker
~~~

Observe bounty data, status, tags, history arrays, withdrawable balances, and the actual contract ETH balance.

Then attack the system with wrong callers, early actions, double actions, bad reputation, and failed ETH transfers.

## 36. Security questions

### Authorization

Who can call this? Who should be able to call this?

### State

What exact state must exist first? Can the action happen twice?

### Accounting

Where is ETH physically stored? What storage says someone is entitled to it? Can the entitlement be credited twice?

### External calls

What contracts are called? What happens when they revert or behave unexpectedly?

### Hashing

Exactly which bytes are hashed? Could different inputs encode ambiguously?

### Data relationships

Does every ID point to the intended bounty? Can history drift away from the main mapping?

## 37. Break the protocol

Try:

~~~text
unknown ID
zero-value bounty
wrong caller
creator claims own bounty
low reputation
claim twice
submit too early
submit twice
approve too early
complete twice
cancel after claim
cancel after completion
cancel twice
withdraw twice
resolve twice
non-owner resolution
failed ETH transfer
unexpected direct ETH
~~~

Then look for higher-level invariants.

For example:

> A bounty's committed ETH must never be credited to two different users through two different terminal paths.

## 38. Historical comparison

Only after your rebuild is complete, inspect the existing implementation.

Compare the struct, mappings, arrays, ID generation, hashing, reputation interface, state transitions, ETH accounting, withdrawals, events, errors, and direct ETH handling.

Do not just ask what is different. Ask what your earlier misunderstanding was and whether you would make the same design mistake now.

## Final architecture

~~~text
                         BountyArena
                              │
             ┌────────────────┼────────────────┐
             │                │                │
          Ownable        Reputation        Bounty data
             │            interface            │
             │                │                ▼
        onlyOwner             │          bytes32 → Bounty
             │                │                │
             │                │        ┌───────┼───────┐
             │                │        │       │       │
             │                │     creator  hunter  tags[]
             │                │     amount   status
             │                │     solutionHash
             │                │
             │                ▼
             │          external call
             │
             ▼
      dispute resolution

user address → uint256
       ↓
withdrawable ETH

address → bytes32[]
       ↓
creator bounty history

bytes32[]
   ↓
global bounty IDs
~~~

## Final objective

The finished system should let a user create a funded bounty, identify it by a bytes32 ID, store it in connected data structures, verify reputation, move through explicit states, store a hashed solution, approve or dispute the bounty, credit the correct party, and withdraw ETH safely.

The project is successful when you can explain not only what each component does, but why the components have to work together in that order.