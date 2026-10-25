# When to use a getter

**Type:** concept / quick reference

**Related notes:** [Visibility and automatic getters](./solidity-visibility-and-automatic-getters.md), [Visibility and getters cheatsheet](./solidity-visibility-getters-cheatsheet.md), [Knowledge Map](../MAP.md).

## My words

> so basically getters are just useful outside the contract

## Explanation

That is basically right for the automatic getter that Solidity generates from a `public` state variable. Its main use is letting an outside caller read the state through the contract's external interface.

Inside the same contract, use the state variable directly by name:

```solidity
uint256 public value = 10;

function doubleValue() external view returns (uint256) {
    return value * 2;
}
```

Inside the contract, the function uses `value`, not `value()`.

Outside the contract, a caller can read it through the generated getter, for example `contract.value()`.

A custom getter can still be useful when it returns a calculated result, combines information, or exposes selected information from a `private` state variable. For this SimpleStorage exercise, `uint256 public value;` already provides `value()`, so a separate `checkvalue()` is unnecessary if it only returns `value`.

## Quick rule

- Inside the same contract: `value`
- Outside the contract: `contract.value()`
- Custom getter: useful when it does more than returning a public state variable unchanged.
