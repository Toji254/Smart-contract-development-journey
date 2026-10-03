# ETH Escrow

## What you are building

You are going to build a simple ETH escrow from an English description.

~~~text
Creator
   │
   │ deposit ETH
   ▼
Escrow
   │
   │ recipient accepts
   ▼
Accepted
   │
   │ creator releases
   ▼
Recipient receives ETH
~~~

The important lesson is how actors, state, authorization, and ETH movement fit together.

## 1. Define the actors

### Creator

The person who creates and funds an escrow.

### Recipient

The person who is supposed to receive the ETH.

Write down who may perform each action before coding.

## 2. Define the lifecycle

Start with this state machine:

~~~text
CREATED
   │
   │ recipient accepts
   ▼
ACCEPTED
   │
   │ creator releases
   ▼
RELEASED
~~~

Cancellation:

~~~text
CREATED → CANCELLED
~~~

For the core exercise, use a concrete rule: the creator may cancel only before acceptance, and cancellation refunds the creator.

Deadlines and disputes are stretch goals.

## 3. Decide what an escrow must remember

At minimum:

~~~text
creator
recipient
amount
status
id
~~~

This naturally suggests a struct.

## 4. Add a status enum

Use states that match the lifecycle.

The important part is not the syntax. The important part is defining which states each function may enter.

## 5. Support more than one escrow

Do not hard-code a single storage slot.

Use a unique identifier, for example a bytes32 escrow ID, and map that ID to an escrow struct.

Your storage should conceptually be:

~~~text
mapping(bytes32 => Escrow)
~~~

Ask:

> If Alice creates two escrows, how does the contract distinguish them?

## 6. Create an escrow

The creator sends ETH with the creation transaction.

Use msg.value as the source of truth for the ETH actually deposited.

Do not confuse a function parameter with ETH attached to the transaction.

Conceptual flow:

~~~text
creator calls create
        ↓
validate inputs
        ↓
read msg.sender
        ↓
read msg.value
        ↓
generate escrow ID
        ↓
store Escrow struct
        ↓
emit event
~~~

## 7. Validate participants

At minimum, decide what should happen when the recipient is the zero address, creator and recipient are the same address, or msg.value is zero.

Write tests for the rules you choose.

## 8. Test creation first

Prove that valid creation stores the correct creator, recipient, amount, and initial state, and that ETH arrives at the contract.

Do not continue until you understand what changed on-chain.

## 9. Let the recipient accept

Only the stored recipient may call accept.

The valid transition is:

~~~text
CREATED → ACCEPTED
~~~

Test wrong caller, repeated acceptance, and acceptance from terminal states.

## 10. Release the ETH

The release rule is:

~~~text
only creator
+
status == ACCEPTED
=
release is allowed
~~~

Then move the state to RELEASED and send the escrowed ETH to the recipient.

## 11. Think about transfer ordering

ETH transfer is an external interaction.

Reason about:

~~~text
checks
  ↓
state transition
  ↓
external ETH interaction
~~~

Ask what a contract recipient could do during the transfer.

## 12. Make release one-time

An escrow must not be payable twice.

Test:

~~~text
release once  → succeeds
release again → reverts
~~~

Do not depend only on the contract balance changing. The escrow itself needs terminal state.

## 13. Add cancellation

Core rule:

~~~text
CREATED → CANCELLED
~~~

Only the creator can cancel the basic version.

Test cancellation before acceptance and rejection after the escrow has moved past the allowed state.

## 14. Add events

Emit events for creation, acceptance, release, and cancellation.

Remember the distinction:

~~~text
state  = what the contract remembers
event  = what the transaction log announces
~~~

## 15. Minimum test matrix

### Creation

- [ ] valid creation succeeds;
- [ ] amount equals actual ETH deposited;
- [ ] creator and recipient are recorded correctly;
- [ ] initial state is CREATED;
- [ ] invalid participant setup fails;
- [ ] zero-value creation fails if that is your chosen rule.

### Acceptance

- [ ] recipient can accept;
- [ ] wrong caller cannot;
- [ ] state becomes ACCEPTED;
- [ ] acceptance cannot happen twice.

### Release

- [ ] creator cannot release before acceptance;
- [ ] non-creator cannot release;
- [ ] creator can release after acceptance;
- [ ] recipient receives the correct amount;
- [ ] state becomes RELEASED;
- [ ] second release fails.

### Cancellation

- [ ] creator can cancel when allowed;
- [ ] unauthorized caller cannot;
- [ ] released or otherwise ineligible escrow cannot cancel;
- [ ] funds return to the intended party;
- [ ] cancellation cannot be processed twice.

## 16. Manual interaction

Use Anvil with separate creator, recipient, and attacker accounts.

Perform:

~~~text
creator creates
recipient accepts
creator releases
recipient receives ETH
~~~

Then attack the flow with wrong callers, early release, double release, and late cancellation.

## 17. Stretch goals

After the basic version is boringly correct:

- deadline / expiry;
- multiple escrows per user;
- participant history and discovery;
- dispute resolution.

Each stretch goal should introduce a new state or accounting question.

## 18. Historical comparison

Only after your rebuild is complete, inspect src/EthEscrow.sol.

Compare storage design, IDs, msg.value, state transitions, caller checks, ETH transfer order, repeated actions, cancellation, and tests.

## Final mental model

~~~text
                Escrow[id]
                    │
             ┌──────┴──────┐
             │             │
          creator       recipient
             │             │
             │             │ accept
             │             ▼
             │          ACCEPTED
             │             │
             │             │ release
             ▼             ▼
                RELEASED
                   │
                   ▼
               Recipient
~~~

The project is successful when you can explain who can change each state, why they can change it, where the ETH is, and why the same ETH cannot be released twice.