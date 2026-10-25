# Solidity visibility and automatic getters

**Type:** concept / syntax / clarification  
**Date captured:** 2026-10-25

## Where this came from

**Exercise:** Rebuilding `SimpleStorage` from scratch and asking how public state variables, getters, and mapping lookups work.

**Project:** [SimpleStorage refresher contract](../../SImple%20Storage/src/SimpleStrorage.sol)  
**Related note:** [Constructor, state variable, setter, and getter](./simple-storage-constructor-setter-getter.md)  
**Related note:** [Mapping keys and values](./simple-storage-mapping-access.md)  
**Knowledge map:** [Knowledge Map](../MAP.md)

## My words

> cool and about the getter part I know when sumn is public in solidity it gives it a getter explain say even for mapping we usually do mapping[key] to get the value either way and also explain for anything that can be public functions,state variables,local variables etc

Then I asked:

> wait are these the only things that can be public in solidity

Keep these questions as they were asked. The explanation below adds the technical detail without replacing my wording.

---

## 1. Public state variable: automatic getter

When a **state variable** is declared `public`, Solidity automatically generates a getter function so external callers can read the stored value.

```solidity
uint256 public value;
```

Solidity generates a getter that external callers can use as `value()`. This does not generate a setter. If the value should be changeable after deployment, the contract still needs a function that assigns a new value.

For example:

```solidity
function setValue(uint256 _value) external {
    value = _value;
}
```

The getter reads the current value; the setter changes it. See [the constructor/setter/getter note](./simple-storage-constructor-setter-getter.md).

## 2. Mapping lookup inside Solidity versus its generated getter

Consider:

```solidity
mapping(address => uint256) public balances;
```

The mapping stores a number for each address.

### Inside the contract

Use square brackets to look up a mapping entry:

```solidity
uint256 amount = balances[alice];
```

Here, `balances[alice]` gets the value stored under Alice's address. This is mapping access syntax.

### Outside the contract

Because `balances` is public, the compiler generates a getter that accepts an address. An external caller uses the function-call form, conceptually:

```text
balances(aliceAddress)
```

This asks for the same entry, but through the getter in the contract's external interface.

The generated getter behaves conceptually like this (illustration only; do not add another function with the same name):

```solidity
function balances(address account)
    external
    view
    returns (uint256)
{
    return balances[account];
}
```

**The important distinction:** `balances[alice]` is mapping access from Solidity code, while `balances(aliceAddress)` is a call to the generated getter from outside the contract.

A public mapping getter returns the entry for the supplied key. It does not automatically return every entry in the mapping.

The same idea applies to public arrays: inside Solidity, `numbers[0]` reads the first array element; outside the contract, the generated getter is called with an index, conceptually `numbers(0)`. The generated getter does not automatically return the full array.

## 3. What can have the visibility setting `public`?

The key is to distinguish **things that have a visibility setting** from **things that are publicly callable or observable**.

| Solidity item | Can it be declared `public`? | Explanation |
| --- | --- | --- |
| State variable | Yes | Generates an automatic getter. This can include ordinary values and state variables whose types are mappings or arrays. |
| Function | Yes | Can be called from outside the contract and from within the contract. |
| Mapping or array as a local variable | No | The local variable itself has no visibility setting. A mapping or array declared as a state variable can be public. |
| Local variable | No | Exists within a function's execution; it is not a contract-level public declaration. |
| Function parameter | No | Receives an argument for that call; it has no visibility setting. |
| Constructor | Not in modern Solidity syntax | Runs during deployment and does not use `public` visibility. |
| Event | No | Events are declared and emitted; they have no `public` visibility setting. |
| Struct or enum type declaration | No | Defines a type rather than an externally callable function or state variable. A state variable whose type is a struct can itself have visibility. |
| Modifier or custom error | No | These declarations do not use `public` visibility. |

### State variable visibility

- `public`: accessible from inside Solidity and has a generated external getter.
- `internal`: accessible within the contract and its derived contracts; no automatic external getter. This is the default visibility for state variables.
- `private`: directly accessible only within the contract where it is declared; no automatic external getter.
- State variables do not have `external` visibility.

Making a state variable `private` does **not** make blockchain data secret. It restricts access through Solidity's language rules; the data may still be inspectable from blockchain data.

### Function visibility

- `public`: callable from within the contract and from outside it.
- `external`: intended to be called from outside the contract. An external function can also be invoked with `this.functionName(...)`, which makes an external call; a plain internal call like `functionName(...)` is not allowed for an external-only function.
- `internal`: callable within the current contract and derived contracts.
- `private`: callable only within the contract where it is declared.

Function visibility does not itself say whether the function changes state or reads state. Function body, mutability keywords, and any access checks determine that behavior.

### Local variables and parameters

A local variable is declared inside a function, and a parameter receives an argument for one function call. Neither can be marked `public`, `private`, `internal`, or `external`.

If an outside caller needs a calculation result, the function can return it:

```solidity
function calculate() external pure returns (uint256) {
    uint256 result = 10 + 5;
    return result;
}
```

Here, `result` is local. The caller receives `15` as the function's return value; Solidity does not create a getter for `result`.

## 4. The SimpleStorage takeaway

For this exercise:

```solidity
uint256 public value;
```

automatically generates `value()` for reading the current state variable. A separate `checkvalue()` is unnecessary if its only job is to return `value`, though it can be kept for practice.

The generated getter does not allow users to modify `value`. The setter, increment, and decrement functions must be written separately.

## Memory rule

- **Public state variable** → Solidity generates a getter.
- **Public function** → the function I wrote can be called externally and internally.
- **Local variable / parameter** → no visibility setting and no automatic getter.
- **Public mapping / array state variable** → generated getter reads an individual entry by key or index.
- **`private`** → does not mean the underlying blockchain data is secret.

Official reference: [Solidity documentation — Visibility and Getters](https://docs.soliditylang.org/en/latest/contracts.html#visibility-and-getters).
