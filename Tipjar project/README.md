# Tipjar

Tipjar is a deliberately small ETH accounting project.

Its job is to teach the basics of receiving ETH, recording who paid, and restricting withdrawals to an owner.

---

## 1. Core idea

```
User
  |
  | send ETH
  v
Tipjar contract
  |
  +--> record user's cumulative tips
  |
  v
Contract balance
  |
  | owner withdrawal
  v
Recipient
```

The project is small on purpose.

It is a good place to become comfortable with:

- payable functions;
- `msg.value`;
- mappings;
- contract balances;
- owner-only actions;
- ETH transfers;
- events.

---

## 2. What the historical code contains

The current source contains:

- an immutable `OWNER`;
- an `onlyowner` modifier;
- `mapping(address => uint256) usertips`;
- a tip event;
- a payable tip function;
- an unfinished withdrawal function.

It is **not a completed contract**.

Important problems include:

- the mapping is never actually incremented;
- the local `tip` parameter does not provide persistent accounting;
- `msg.value` is transaction data, not a mutable storage variable;
- the withdrawal declaration is unfinished/malformed;
- there are no meaningful tests.

Treat this as an old scaffold and rebuild it cleanly.

---

## 3. Rebuild specification

### Tipping

Anyone can send an ETH tip.

A valid tip should:

1. enter the contract;
2. increase that sender's cumulative tip total;
3. emit a useful event.

Suggested accounting:

```
usertips[msg.sender] += msg.value;
```

The exact implementation is yours to decide.

### Withdrawal

Only the owner can withdraw.

The withdrawal operation should be able to specify:

- amount;
- recipient.

It should reject an amount larger than the contract's current balance.

The contract should use a deliberate ETH transfer pattern and handle failure correctly.

---

## 4. Two balances you must keep separate

This is an important concept for the rebuild.

### Historical tips

```
usertips[user]
```

This should represent how much ETH that address has tipped **through the contract over its lifetime**.

### Current contract balance

```
address(this).balance
```

This represents how much ETH the contract currently holds.

A withdrawal can reduce the contract balance without reducing a user's historical tipping total.

These values answer different questions.

---

## 5. Minimum tests

### Tipping

- [x] user can send a tip;
- [ ] user's cumulative tips increase;
- [x] contract balance increases;
- [x] event is emitted;
- [ ] repeated tips accumulate.

### Withdrawal

- [x] non-owner cannot withdraw;
- [ ] owner can withdraw a valid amount;
- [x] recipient receives the correct amount;
- [ ] over-withdrawal reverts;
- [ ] failed withdrawal does not corrupt state;
- [ ] multiple withdrawals behave correctly.

---

## 6. Questions to answer while rebuilding

Before coding, be able to answer:

- What exactly does `msg.value` represent?
- Where does ETH go when a payable function succeeds?
- What is the difference between storage accounting and actual ETH balance?
- Why does `onlyowner` check `msg.sender`?
- What happens if the recipient is a contract?
- What should happen when the recipient rejects ETH?
- Should zero-value tips be allowed?
- Should the owner be allowed to withdraw the entire balance?
- Should withdrawals affect `usertips`?

These questions matter more than the final number of lines in the contract.

---

## 7. Stretch goals

After the core version works:

- allow user-facing tip messages;
- expose total tips received;
- emit a dedicated withdrawal event;
- support a `receive()` function deliberately, with a clear accounting policy;
- write stronger invariants around balance and accounting.

---

## 8. Rebuild rule

Start from the behavior described above.

Do not attempt to repair the old function line by line.

The old implementation is there so that, after rebuilding, you can compare your current understanding against your earlier attempt.
