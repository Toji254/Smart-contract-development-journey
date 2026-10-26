# Using an interface type: addresses and constructors

**Type:** concept / syntax / discovery  
**Date captured:** 2026-10-26

## Where this came from

**Project:** [Token Sale Contract](../../Token%20Sale%20Contract/README.md)  
**Related note:** [Interfaces: inheritance vs interacting through a reference](./solidity-interface-inheritance-vs-interaction.md)  
**Knowledge map:** [Knowledge Map](../MAP.md)

---

## My words

> another thing when we use the interface as a type do we like a must need constructors and do we need to supply an address give me the rules

Keep the question as asked. It records the next gap after understanding that an interface variable can refer to another contract.

---

## Explanation

**An interface does not need a constructor.** An interface describes function signatures; it does not create an instance of a contract.

A contract that uses an interface as a type does **not automatically need a constructor either**. The real question is: how will the code know which deployed contract it wants to call?

Start here:

```solidity
IWallet wallet;
```

This declares a variable named `wallet` whose type is `IWallet`. By itself, it does not identify a particular deployed wallet.

To call a particular deployed contract through an interface, the code needs to obtain that contract's address somehow.

### Option A: Provide the address during deployment

```solidity
contract WalletUser {
    IWallet wallet;

    constructor(address walletAddress) {
        wallet = IWallet(walletAddress);
    }
}
```

- `IWallet wallet` declares a stored reference using the interface type.
- `address walletAddress` receives an address during deployment.
- `IWallet(walletAddress)` treats that address as a reference through the `IWallet` interface.
- `wallet = ...` stores the reference so later function calls can use it.

The constructor belongs to `WalletUser`, not to `IWallet`. The conversion does not deploy a new wallet and does not prove that the address really implements `IWallet`.

### Option B: Provide the address to a function

```solidity
function useWallet(address walletAddress) external {
    IWallet wallet = IWallet(walletAddress);
    // Use wallet here.
}
```

Here the address is supplied each time the function is called. The `wallet` variable is local, so this reference is not permanently stored as a state variable.

### Option C: Assign the reference another way

A contract could store a reference assigned through another mechanism, such as a setter function. Access control and whether that address is allowed to change would then be design decisions.

## Rules to remember

1. An interface itself does not have a constructor.
2. A contract using an interface type does not automatically need a constructor.
3. To call a particular deployed contract through an interface, the code needs its address somehow.
4. A constructor is one way to receive and store that address; a function parameter or another assignment mechanism can also provide it.
5. `IWallet(walletAddress)` creates a typed reference to that address. It does not deploy the target or prove the target supports the interface.
6. If a stored interface variable is never assigned the intended target address, it is not connected to that deployed contract, and calls through it will not work as intended.

## What clicked

An interface doesn't force a constructor on the contract that uses it. The constructor is a design choice for how the contract gets the address it should communicate with.

For `TokenSaleContract`, passing the LK token's address to the sale constructor is useful if the sale should keep using that same deployed token for future purchases. That requirement comes from the sale's design, not from `IERC20` itself.

## Connections

```text
IERC20 / IWallet interface type
  └── variable holds a contract reference
        ├── needs a target address
        ├── constructor can provide and store the address
        ├── function parameter can provide an address temporarily
        └── function calls go to the referenced contract
```

- [Interfaces: inheritance vs interacting through a reference](./solidity-interface-inheritance-vs-interaction.md) — distinguishes implementing an interface from using it to call another contract.
- [Token Sale project brief](../../Token%20Sale%20Contract/README.md) — the sale needs to know which deployed token it will distribute.
- [Knowledge Map](../MAP.md) — links interfaces, inheritance, and external calls.

---

## My current version

Declaring an interface-typed variable does not automatically connect it to a deployed contract. The code needs the target address somehow. A constructor is one way to receive and store that address, but it is not required just because an interface type is used.
