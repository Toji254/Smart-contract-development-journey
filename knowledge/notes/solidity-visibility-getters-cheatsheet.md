# Solidity Cheatsheet: Visibility, Public, and Getters

**Type:** concept / syntax / quick reference  
**Date captured:** 2026-10-25

**Project:** [SimpleStorage refresher contract](../../SImple%20Storage/src/SimpleStrorage.sol)  
**Full explanation:** [Solidity visibility and automatic getters](./solidity-visibility-and-automatic-getters.md)  
**Knowledge map:** [Knowledge Map](../MAP.md)

## My request

> give me a cheatsheet for this I don't want to read all that explanation

## 1. What does `public` do?

| Declaration | What happens? |
| --- | --- |
| `uint256 public value;` | Automatically generates getter `value()`. |
| `mapping(address => uint256) public balances;` | Generates a getter for one address's balance. |
| `uint256[] public numbers;` | Generates a getter for one array index. |
| `function setValue() public {}` | Function can be called externally and internally. |
| Local variable / parameter | Cannot be declared `public`. |

## 2. Mapping and getter syntax

```solidity
mapping(address => uint256) public balances;
```

| Where? | Syntax | Meaning |
| --- | --- | --- |
| Inside Solidity | `balances[alice]` | Read Alice's entry with mapping brackets. |
| Outside, through the contract | `contract.balances(alice)` | Call the generated getter. |
| Outside, single state variable | `contract.value()` | Read the current value. |

A public mapping getter reads one key at a time, not the entire mapping.

## 3. Visibility keywords

### State variables

| Keyword | Who can access it in Solidity? | Auto getter? |
| --- | --- | --- |
| `public` | Inside and externally through getter | Yes |
| `internal` | Declaring contract and derived contracts | No |
| `private` | Declaring contract only | No |

State variables do not have `external` visibility.

### Functions

| Keyword | Who can call it? |
| --- | --- |
| `public` | Inside and outside |
| `external` | Outside; `this.functionName(...)` is also possible but makes an external call |
| `internal` | Declaring contract and derived contracts |
| `private` | Declaring contract only |

### Local variables and parameters

- Cannot be declared `public`, `private`, `internal`, or `external`.
- Do not get automatic getters.
- Return a value from a function when the caller needs a result.

## 4. Three rules to remember

1. **Public state variable = automatic getter, not setter.**
2. **Public function = the function you wrote can be called internally and externally.**
3. **Private does not mean secret** — blockchain data may still be inspectable.

For this `SimpleStorage` exercise, `uint256 public value;` already gives you `value()`. You still need your own setter, increment, and decrement functions to change it.
