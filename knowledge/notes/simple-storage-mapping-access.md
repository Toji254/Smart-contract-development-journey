# SimpleStorage refresher: mapping keys and values

**Type:** concept / syntax / mistake / discovery  
**Date captured:** 2026-10-25

## Where this came from

**Exercise:** Writing a `SimpleStorage` contract from scratch to wake up my Solidity knowledge after a break. The exercise is still in progress; this note captures the first mapping-access mistake, not a claim that the whole contract is finished.

**Project:** Scratch `SimpleStorage` refresher (no separate project README yet).

**Related notes:**
- [Knowledge Map](../MAP.md)
- [Study Notes index](README.md)

---

## My understanding

> cool I see where I made a mistake.

> keep in mind I'm writing this simple storage from scratch to remind myself of solidity

Keep this wording as part of the learning history; the technical explanation sits beside it rather than replacing it.

---

## The code I was trying to write

```solidity
// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.20;

contract SimpleStorage {
    // uint256 value;
    mapping(address => uint256 number) private value;

    function checkvalue() external view returns (uint256) {
        return value.[number];
        // value[]
    }
}
```

The mistake was in the lookup expression: `value.[number]`. Mapping access uses square brackets directly after the mapping name, and the bracket must contain a key of the mapping's key type.

---

## Explanation

A mapping can be thought of as a table where an address points to a number.

| Address (key) | Number (value) |
| --- | ---: |
| Alice's address | 100 |
| Bob's address | 250 |
| Charlie's address | 50 |

For this declaration:

```solidity
mapping(address => uint256 number) private value;
```

- `address` is the type of key used to look something up.
- `uint256` is the type of value stored for each key.
- `number` is the optional name given to the mapped value in the declaration. It is not an address and is not a separate variable that I can use as the lookup key.
- `value` is the name of the mapping itself.
- `private` means the variable is not directly exposed through Solidity's normal automatically generated public getter. It does not make blockchain storage secret.

### What was wrong with the lookup?

I wrote:

```solidity
return value.[number];
```

There are two issues:

1. **Syntax:** mapping access is written as `value[key]`, with no dot between the mapping name and the square bracket.
2. **Wrong thing inside the bracket:** the mapping expects an `address` key. `number` names the stored value; it is not the address used to find that value.

The key question to ask whenever accessing a mapping is: **“What key am I using to retrieve this value?”**

If the intended behavior is to read the number associated with the person calling the function, the lookup is:

```solidity
return value[msg.sender];
```

`msg.sender` is the address of the caller of the current call. If Bob calls the function, Solidity looks up the entry keyed by Bob's address. It does not look up Alice's entry just because Alice has a value in the same mapping.

A corrected version of the current reading function is:

```solidity
// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.20;

contract SimpleStorage {
    mapping(address => uint256 number) private value;

    function checkvalue() external view returns (uint256) {
        return value[msg.sender];
    }
}
```

This version compiles, but it has no function that writes a number into the mapping yet. A mapping entry for an address that has never been assigned a value reads as the default value of its value type. For `uint256`, that default is `0`, so `checkvalue()` returns `0` until a value is stored for the caller.

### Quick example

If Alice's entry is `value[Alice] = 100` and Bob's entry is `value[Bob] = 250`, then when Bob calls `checkvalue()`, `msg.sender` is Bob's address and the lookup returns `250`.

---

## What clicked

The mapping name, key, and mapped value are different things:

```text
value             → the whole mapping
address           → the required key type
number            → the name of the mapped uint256 value
value[msg.sender] → look up the value stored for the caller's address
```

Before writing a mapping lookup, identify the key type and decide which actual key expression should go inside the brackets.

---

## Connections

```text
SimpleStorage refresher
  ├── mapping declaration
  │    ├── key type: address
  │    └── mapped value: uint256
  ├── mapping lookup: value[key]
  │    └── caller-based lookup: value[msg.sender]
  ├── function visibility: external
  ├── read-only function: view
  ├── return type: uint256
  └── default value: uint256 starts at 0
```

Related Solidity ideas:
- [Knowledge Map](../MAP.md) — mappings, storage, and EVM reasoning.
- This also connects to future `SimpleStorage` steps: writing a value to a mapping, then checking which key the read function uses.
- [Constructor, state variable, setter, and getter](./simple-storage-constructor-setter-getter.md) — how the constructor initializes a shared value and how a later function changes it.

---

## Later discovery / correction

The note captures the current understanding. When the contract grows, add the setter and test multiple callers rather than silently replacing this explanation. The mapping lookup mistake should remain visible as part of the learning history.

---

## My current version

A mapping lookup needs an actual key in square brackets. For `mapping(address => uint256)`, use an address expression such as a function parameter or `msg.sender`. The name `number` in the declaration names the mapped value; it is not the key.
