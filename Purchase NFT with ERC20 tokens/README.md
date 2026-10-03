# Purchase NFT with ERC20 Tokens

## What you are building

You are going to build a small system where a buyer pays with an ERC20 token and receives an ERC721 NFT.

~~~text
Buyer
  │
  │ approve purchase contract
  ▼
ERC20 allowance
  │
  │ purchase()
  ▼
Purchase contract
  │
  ├── transferFrom() pulls payment
  │
  └── mint NFT
          │
          ▼
       Buyer owns NFT
~~~

This is where you stop thinking about one contract in isolation.

## 1. Understand the two standards separately

### ERC20

Understand:

- balance;
- allowance;
- approve;
- transfer;
- transferFrom.

### ERC721

Understand:

- unique token IDs;
- ownership;
- minting.

Do not combine the standards until you can explain each one separately.

## 2. Define the actors

At minimum:

- buyer;
- seller / treasury / owner;
- ERC20 token contract.

## 3. Choose a simple architecture

A reasonable beginner architecture is:

~~~text
ERC20 token
     │
     │ transferFrom
     ▼
PurchaseNFT
     │
     │ mint
     ▼
Buyer
~~~

Your purchase contract should know which token is accepted, what the price is, and where payment goes.

## 4. Create a local payment token

For testing, create or use a mock ERC20.

Give the buyer enough tokens to perform the exercise.

Now your local environment contains:

~~~text
token balance
+
token allowance
+
NFT purchase
~~~

## 5. Understand approve

Suppose Alice owns 100 tokens.

She first approves the purchase contract to spend up to a chosen amount.

Conceptually:

~~~text
Alice
  │
  │ approve(PurchaseNFT, amount)
  ▼
ERC20 allowance
~~~

Balance and allowance are different:

balance = what Alice owns
allowance = what the spender is permitted to move

## 6. Understand transferFrom

During purchase, the purchase contract can request the ERC20 contract to move tokens from the buyer to the intended payment recipient.

Conceptually:

~~~text
Alice
  │
  │ transferFrom
  ▼
payment recipient
~~~

The purchase depends on that external call succeeding.

## 7. Build the NFT collection independently

Before combining payment with minting, make sure the NFT side works.

Decide:

- collection name;
- collection symbol;
- token ID strategy.

Be careful with counters: the returned token ID should correspond to the token actually minted.

## 8. Add the price

Keep the first version simple, for example a fixed ERC20 price.

Conceptually:

~~~text
buyer pays price
       +
purchase succeeds
       =
buyer receives one NFT
~~~

Decide who controls the price. Immutable pricing is a simple first version; owner-controlled pricing can be a later exercise.

## 9. Write the purchase flow on paper

Before coding:

~~~text
1. identify buyer
2. check purchase conditions
3. collect ERC20 payment
4. mint NFT
5. emit purchase event
~~~

Ask what happens if payment fails and what happens if minting fails.

Both should leave the transaction in a safe final state.

## 10. Add the ERC20 interface

Your purchase contract only needs the external functions it calls.

This teaches:

~~~text
interface
   ↓
external contract address
   ↓
external call
~~~

## 11. Implement purchase

The intended user journey is:

~~~text
approve()
   ↓
allowance
   ↓
purchase()
   ↓
transferFrom()
   ↓
mint()
   ↓
buyer owns NFT
~~~

Get this one path working before adding supply limits or other features.

## 12. Test the payment side

Cover:

- insufficient ERC20 balance;
- insufficient allowance;
- valid approval;
- exact payment amount;
- correct payment recipient.

Inspect the buyer and payment recipient balances after the purchase.

## 13. Test the NFT side

After purchase, prove actual NFT ownership and the exact token ID.

Do not stop at “the transaction did not revert.”

## 14. Think about ordering

The purchase function combines an external token call with NFT minting.

Ask:

- What if the token contract reverts?
- What if the token behaves maliciously?
- What if minting fails?
- Can state become inconsistent?

After the basic version works, compare a raw interface approach with safer ERC20 transfer helpers.

## 15. Emit a purchase event

Useful information may include buyer, token ID, and price.

Events should make the lifecycle observable without pretending to replace storage.

## 16. Minimum test matrix

### Payment

- [ ] insufficient balance fails;
- [ ] insufficient allowance fails;
- [ ] valid approval succeeds;
- [ ] correct amount is transferred;
- [ ] intended recipient receives payment.

### NFT

- [ ] buyer receives NFT;
- [ ] token ID is unique;
- [ ] reported token ID matches the minted token;
- [ ] ownership is correct.

### Full purchase

- [ ] valid purchase succeeds;
- [ ] payment and mint are atomic;
- [ ] failed payment does not mint;
- [ ] failed mint does not leave a completed purchase.

## 17. Manual interaction

Using Anvil:

~~~text
1. inspect buyer token balance
2. approve PurchaseNFT
3. inspect allowance
4. call purchase
5. inspect buyer token balance
6. inspect payment recipient balance
7. inspect NFT ownership
8. inspect token ID
~~~

This is the moment the separate Solidity concepts become one live flow.

## 18. Stretch goals

Only after the basic version works:

- fixed supply;
- per-wallet limit;
- owner-controlled price;
- pause;
- multiple payment tokens;
- metadata;
- malicious ERC20 behavior tests.

## 19. Break the purchase system

Try purchases without approval, with insufficient balance, repeatedly, after supply limits, and with unexpected token behavior.

Then ask two core questions:

> Can payment ever be collected without minting?

> Can an NFT ever be minted without collecting the required payment?

Those are core invariants.

## 20. Historical comparison

Only now inspect src/PurchaseNFT.sol.

Compare the token counter, owner handling, mint function, NFT ownership, missing payment flow, allowances, transferFrom, and tests.

## Final mental model

~~~text
Alice owns ERC20
       │
       │ approve()
       ▼
allowance[alice][PurchaseNFT]
       │
       │ purchase()
       ▼
PurchaseNFT
   │        │
   │        └──── transferFrom()
   │
   └───────────── mint()
                  │
                  ▼
            Alice owns NFT
~~~

The lesson is that approval, transfer, payment accounting, ERC721 minting, ownership, and transaction atomicity form one connected system.