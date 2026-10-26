# Solidity interfaces: inheritance vs interacting through a reference

**Type:** concept / syntax / project / discovery / correction  
**Date captured:** 2026-10-26

## Where this came from

**Project:** [Token Sale Contract](../../Token%20Sale%20Contract/README.md)  
**Current sale draft:** [Token Sale Contract.sol](../../Token%20Sale%20Contract/src/Token%20Sale%20Contract.sol)  
**Token implementation:** [Token.sol](../../Token%20Sale%20Contract/src/Token.sol)  
**Related project:** [Purchase NFT with ERC20 Tokens](../../Purchase%20NFT%20with%20ERC20%20tokens/README.md)  
**Knowledge map:** [Knowledge Map](../MAP.md)

---

## My words

> they are like implementations and we use them if we want our contract to act a certain way that another contract does without making our contract the other one or building it anew Idk if you get what I mean problem is actually using or writing the interface in our contract TokenSaleContract that I'm working on I can't seem to figure out what next after importing the interface I mean should I infer to the ERC20 too and set the constructor in our child contract or what also remember I need to come to the conclusion you are teaching me not giving me solutions

> I don't see why remove is isn't is like inheritance a way for IERC20 to talk to our contract or doesnt it need to is talking to and interacting different or is there some rule for interfaces where we don't need to inherit them

> wait then give me the rules is it that we never inherit interface contracts or what do it mean

Keep these questions as they were asked. They capture the difference I was trying to understand: importing an interface, inheriting from it, and using it to call another contract are related but different things.

---

## Explanation

The important rule is:

**You can inherit an interface. You do that when your contract is meant to implement the interface. You can also use an interface as a variable's type when your contract wants to communicate with another contract.**

There is no rule that interfaces must never be inherited. The question is what role the interface has in this contract.

### 1. Import means “make this definition available”

For example:

```solidity
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
```

This makes the `IERC20` definition available in the Solidity file. Importing it does not deploy a token, connect to a deployed token, or automatically make the current contract implement it.

### 2. Inheritance means “my contract implements or extends this”

My token currently has this shape:

```solidity
contract Token is ERC20("LOKI", "LK") {
}
```

Here, `Token` inherits from OpenZeppelin's `ERC20` implementation. That implementation provides the standard token functions that `Token` builds on.

By contrast, this declaration in the sale contract:

```solidity
contract TokenSaleContract is IERC20 {
}
```

means that `TokenSaleContract` is claiming to implement the `IERC20` interface. The compiler expects the contract to provide the required interface functions, itself or through inherited implementations. It does **not** mean “use IERC20 to talk to some other token.”

The sale is not supposed to be an ERC-20 token. It is supposed to sell tokens managed by a separate token contract.

### 3. An interface used as a type means “I want to call another contract”

```solidity
IERC20 token;
```

This declares a variable named `token` whose type is `IERC20`. It can hold a reference to a contract through the functions described by that interface.

The declaration by itself does not tell the variable which deployed token to reference. The contract needs to be connected to an address, for example by receiving a token address during deployment and converting that address to the interface type:

```solidity
token = IERC20(_tokenAddress);
```

Read the expression in three pieces:

- `_tokenAddress` identifies the contract address the sale intends to interact with.
- `IERC20(_tokenAddress)` explicitly treats that address as an `IERC20`-typed reference.
- `token = ...` stores that reference in the `token` variable.

This conversion does **not** deploy a token or prove that the address actually contains a compatible ERC-20 contract. It tells Solidity how the code intends to interact with that address.

### 4. What happens when the sale calls a token function?

After `token` has been connected to the token's address, a call such as:

```solidity
token.transfer(buyer, amount);
```

means:

1. Solidity knows the declared type of `token` is `IERC20`.
2. The interface tells Solidity the expected function signature and how to encode the call.
3. The external call is directed to the address stored in `token`.
4. The contract at that address executes the function, if it supports the call, and returns its result or failure.

**The interface describes the conversation. The address directs the conversation. The deployed contract does the actual work.**

### 5. Which import belongs in which contract?

The project has two different responsibilities:

- **`Token.sol`:** builds the actual token, so it inherits an implementation such as OpenZeppelin's `ERC20`.
- **`TokenSaleContract.sol`:** sells tokens created by a separate, deployed token contract. It can use `IERC20` as the type of a variable to interact with that token.

The sale normally does not need to import the concrete `Token` implementation merely because that file exists in the same `src` folder. It would have a reason to import `Token` directly if the sale needed to refer to that concrete type for a specific design choice, such as deploying it itself or using something specific to that contract. For the design chosen in this project, the interface reference keeps the sale from depending directly on that implementation.

Importing a Solidity file and deploying a contract are also different: a file existing in `src` does not mean an instance of it already exists on-chain.

---

## What clicked

There is no blanket rule saying “never inherit interfaces.” The relationship depends on the job:

- **Import:** make a definition available in this file.
- **Inheritance (`is`):** declare that this contract implements or extends that interface/contract.
- **Interface-typed variable (`IERC20 token`):** hold a reference through which this contract can call another contract's functions.
- **Address:** identify which deployed contract the reference points to.

For this token-sale project, the sale contract uses an `IERC20` reference because it needs to **use** the token, not **be** the token.

---

## Connections

```text
Token Sale Contract
  ├── imports IERC20
  ├── keeps an IERC20-typed token reference
  │     ├── gets connected to a deployed token address
  │     └── calls token functions such as transfer
  ├── interacts with a separate Token contract
  └── does not need to inherit IERC20 just to use the token

Token
  └── inherits OpenZeppelin ERC20 implementation
        └── provides the token functionality
```

Related ideas:
- [Token Sale project brief](../../Token%20Sale%20Contract/README.md) — explains the separate token and sale responsibilities.
- [Purchase NFT with ERC20 Tokens](../../Purchase%20NFT%20with%20ERC20%20tokens/README.md) — another project involving ERC-20 interaction.
- [Knowledge Map](../MAP.md) — links interfaces, inheritance, and external contract calls.

---

## Later discovery / correction

An interface is not itself an implementation. Inheriting an interface creates an implementation obligation; declaring a variable of that interface type does not. A cast such as `IERC20(_tokenAddress)` also does not verify that the target contract really conforms to the interface.

---

## My current version

I can inherit an interface when my own contract is supposed to implement its required functions. But if my contract needs to call functions on a separate deployed contract, I can declare a variable using that interface type, connect the variable to the other contract's address, and call functions through the variable. For the token sale, `Token` inherits the ERC-20 implementation, while `TokenSaleContract` uses an `IERC20` reference to interact with the deployed token.
