# Purchase NFT with ERC20 Tokens

This project is an early NFT/payment experiment.

It is useful because the current repository shows the beginning of an ERC721 implementation, while the **ERC20 purchasing mechanism implied by the project name was never completed**.

---

## 1. What the project is supposed to become

The intended concept is a buyer paying with ERC20 tokens and receiving an NFT.

Conceptually:

```
Buyer
  |
  | ERC20 approve
  v
Purchase contract
  |
  | transferFrom()
  v
Payment received
  |
  | mint
  v
Buyer receives ERC721
```

---

## 2. What exists today

The current `src/PurchaseNFT.sol`:

- inherits `ERC721URIStorage`;
- creates an NFT collection called `LOKI254`;
- uses symbol `LOKI`;
- stores an immutable `OWNER`;
- keeps a token counter;
- exposes `mint(address user)`;
- uses `_safeMint`.

There is no completed:

- ERC20 payment token;
- purchase price;
- buyer payment flow;
- `approve` / `transferFrom` interaction;
- purchase function;
- meaningful test suite.

The current `test/PurchaseNFT.t.sol` is empty.

There is also a token-ID detail to investigate: the contract mints with the current counter, increments the counter, and then returns the **new** counter value rather than the ID that was actually minted.

The `OWNER` variable is currently stored but not used by the mint function.

---

## 3. Rebuild target

Because the original repo does not contain a detailed challenge document for this project, use this as a deliberately small specification.

### Payment

- Choose/configure an ERC20 token used for payment.
- Choose/configure a price.
- The buyer must have sufficient ERC20 balance.
- The buyer must have granted enough allowance.
- The purchase contract uses `transferFrom` to collect payment.

### NFT

- A successful purchase mints an NFT to the buyer.
- The token ID returned/emitted identifies the NFT actually minted.
- Token IDs are unique.
- The collection behaves as a valid ERC721.

### Payment destination

The payment should reach the intended seller/owner address according to the chosen design.

### Failure behavior

A purchase should revert when:

- the buyer lacks ERC20 balance;
- allowance is insufficient;
- price/payment conditions are invalid;
- minting conditions are invalid;
- any required authorization is missing.

---

## 4. Core learning topics

This project should make the following flow second nature:

```
ERC20.approve(spender, amount)
        |
        v
allowance[buyer][spender]
        |
        v
purchase()
        |
        +----> ERC20.transferFrom(...)
        |
        +----> NFT mint
        |
        v
buyer owns NFT
```

Understand each part independently before combining them.

Important concepts:

- ERC20 balances;
- ERC20 allowances;
- `approve`;
- `transferFrom`;
- ERC721 ownership;
- token IDs;
- external contract calls;
- access control;
- payment accounting;
- transaction atomicity;
- testing multiple contracts together.

---

## 5. Minimum tests

- [ ] buyer cannot purchase with zero/insufficient balance;
- [ ] buyer cannot purchase without allowance;
- [ ] correct allowance allows purchase;
- [ ] correct ERC20 amount leaves buyer;
- [ ] intended recipient receives payment;
- [ ] NFT is minted to buyer;
- [ ] actual minted token ID is correct;
- [ ] token ownership is correct after purchase;
- [ ] repeated purchases follow the chosen supply rules;
- [ ] unauthorized admin operations revert;
- [ ] a failed purchase leaves state unchanged.

---

## 6. Stretch goals

After the minimum version works:

- fixed supply;
- per-wallet purchase limits;
- metadata/URI management;
- owner-controlled price;
- pause/unpause;
- multiple accepted ERC20 tokens;
- withdrawal/treasury design;
- tests for malicious ERC20 behavior.

These stretch goals start turning a toy into a small protocol, which is exactly where the security questions become more interesting.

---

## 7. Rebuild rule

Do not start by fixing the existing `mint()` function.

Build the payment + NFT flow from the specification, then inspect the old implementation and compare design choices.
