# Tipjar

## What you are building

You are going to build a very small ETH tip jar.

~~~text
Someone sends ETH
       ↓
Tipjar receives it
       ↓
Tipjar remembers who tipped
       ↓
Owner can withdraw ETH
~~~

Do not start from the old implementation. Start from the behavior.

## 1. Understand the problem

Before writing Solidity, answer:

- Where does ETH enter?
- Who sent it?
- Where is the ETH physically stored?
- What must the contract remember?
- Who may withdraw?
- What happens if withdrawal fails?

## 2. Start with the smallest contract

Make the contract exist first. Compile it. Do not add advanced features yet.

~~~bash
forge build
~~~

Checkpoint: understand what the compiler is checking before moving on.

## 3. Decide who the owner is

For this exercise, the deployer becomes the owner.

The important concept is msg.sender: the address that called the current operation.

Ask why owner information belongs in contract state.

## 4. Add owner-only withdrawal

Build a reusable authorization rule:

~~~text
withdraw()
   ↓
Is msg.sender the owner?
   ↓
yes → continue
no  → revert
~~~

Test with an owner and a second account before continuing.

## 5. Make the contract receive ETH

Add a payable tip function.

The ETH attached to that call is msg.value.

Remember:

~~~text
msg.sender = caller
msg.value  = ETH attached to this call
~~~

msg.value is transaction input for the current call, not persistent storage.

## 6. Record who tipped

Now introduce a mapping with the shape:

~~~text
address → uint256
~~~

You want to answer:

> How much ETH has Alice tipped through this contract?

The conceptual relationship is:

~~~text
msg.sender
   ↓
mapping key
   ↓
historical tip amount
~~~

## 7. Keep two balances separate

Historical accounting:

~~~text
usertips[user]
~~~

means how much that address has tipped through the contract over time.

Current contract balance:

~~~text
address(this).balance
~~~

means how much ETH the contract holds right now.

Example:

~~~text
Alice tips 1 ETH
usertips[Alice] = 1 ETH
contract balance = 1 ETH

owner withdraws 0.4 ETH
usertips[Alice] = 1 ETH
contract balance = 0.6 ETH
~~~

Those values answer different questions.

## 8. Emit an event

Emit a tip event containing useful information such as the sender and amount.

Remember:

~~~text
storage = persistent contract state
event   = transaction log information
~~~

Events are not a replacement for storage.

## 9. Test the tipping path

Prove:

~~~text
Alice sends 1 ETH
↓
Alice's total increases by 1 ETH
↓
contract balance increases by 1 ETH
↓
event appears
~~~

Then tip twice and prove the totals accumulate.

## 10. Implement withdrawal

The owner should choose an amount and recipient.

Before the transfer, reason about:

- authorization;
- available balance;
- recipient validity;
- transfer failure;
- external code execution.

Think in terms of:

~~~text
checks
  ↓
state updates
  ↓
external interaction
~~~

## 11. Test withdrawal

Cover:

- owner can withdraw;
- non-owner cannot;
- amount larger than available balance fails;
- repeated withdrawal cannot exceed the real balance;
- recipient receives the correct amount;
- transfer failure is handled.

Also consider what happens if the recipient is a contract.

## 12. Decide the zero-tip policy

Choose explicitly whether zero-value tips are allowed and test the choice.

## 13. Decide the direct-transfer policy

Only after the core path works, think about receive() and fallback().

Ask:

> What happens if ETH is sent directly without calling the tip function?

Possible designs include accepting and counting it, accepting but not counting it, or rejecting it.

Choose deliberately.

## 14. Minimum finished version

### Tipping

- [ ] valid tip succeeds;
- [ ] msg.value is the deposited amount;
- [ ] sender's cumulative total increases;
- [ ] contract balance increases;
- [ ] event is emitted;
- [ ] repeated tips accumulate.

### Ownership

- [ ] deployer becomes owner;
- [ ] only owner can withdraw.

### Withdrawal

- [ ] owner can withdraw;
- [ ] recipient gets the correct amount;
- [ ] over-withdrawal fails;
- [ ] transfer failure is handled;
- [ ] repeat withdrawal cannot duplicate the payout.

## 15. Manual checkpoint

Run Anvil, deploy the contract, and inspect owner, contract balance, and tip totals before and after real local transactions.

Connect the full chain:

~~~text
Solidity source
      ↓
transaction
      ↓
EVM execution
      ↓
storage + balance changes
~~~

## 16. Break it

Try non-owner withdrawal, over-withdrawal, double withdrawal, zero-value tips, failed recipients, and many repeated tips.

Then define invariants such as:

> A withdrawal must never increase the ETH held by the contract.

## 17. Historical comparison

Only after your rebuild works, inspect the old src/Tipjar.sol.

Compare owner setup, mapping updates, msg.value, contract balance, withdrawal logic, events, and failure handling.

The goal is to explain why the old design was incomplete and whether you would make the same mistakes now.

## Final mental model

~~~text
              TIP IN
                │
                │ msg.value
                ▼
        ┌─────────────────┐
        │     Tipjar      │
        │                 │
        │ usertips[user]  │ ← historical accounting
        │                 │
        │ ETH balance     │ ← actual ETH held now
        └────────┬────────┘
                 │
                 │ owner withdrawal
                 ▼
              recipient
~~~

Small contract. Big lesson.