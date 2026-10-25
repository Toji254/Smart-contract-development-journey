# SimpleStorage refresher: constructor, state variable, setter, and getter

**Type:** concept / syntax / discovery / correction  
**Date captured:** 2026-10-25

## Where this came from

**Exercise:** Rebuilding `SimpleStorage` from scratch to refresh Solidity after a break.

**Project:** [SimpleStorage refresher contract](../../SImple%20Storage/src/SimpleStrorage.sol)  
**Related note:** [Mapping keys and values](./simple-storage-mapping-access.md)  
**Knowledge map:** [Knowledge Map](../MAP.md)

---

## My words

> a constructor is what we set and then it's permanent and can't be modified again how comes we are doing that modifying it in this function and as we set the constructor we set the state variable value there so I don't get it

I was treating “the constructor sets the value” as “the value can never change again.” Keep that original confusion here because it marks the point where the distinction clicked.

The mental model I wanted to keep is:

> Constructor: sets the starting value.
>
> State variable: holds the current value.
>
> Setter: changes the current value.
>
> Getter: reads the current value.

---

## Explanation

These are four different roles.

- **Constructor:** runs once when the contract is deployed. It can initialize the state variable with a value chosen for deployment.
- **State variable:** stores the contract's current on-chain value. An ordinary state variable such as `uint256 public value;` is not automatically frozen after the constructor finishes.
- **Setter:** a function that changes the stored value after deployment.
- **Getter:** a function that reads and returns the stored value. Declaring a state variable `public` automatically gives it a getter.

### Start with the constructor

```solidity
uint256 public value;

constructor(uint256 _value) {
    value = _value;
}
```

If the deployer supplies `42`, the constructor assigns `42` to the state variable `value`. The constructor itself does not run again on later calls.

**Important:** the constructor parameter `_value` only exists as a parameter for that constructor execution. It is not the stored state variable. The assignment `value = _value;` is what copies the supplied number into the state variable.

### Then change the value after deployment

```solidity
function setValue(uint256 _value) external {
    value = _value;
}
```

If someone calls `setValue(100)`, the function parameter `_value` receives `100`. Then the line `value = _value;` updates the existing state variable to `100`.

The parameter name `_value` can be reused in the constructor and setter because each parameter belongs to its own function. Reusing the name does not connect the parameters or make them the same variable.

An empty function body does not automatically store the input. Solidity receives the argument into the parameter, but the code in the body must explicitly tell the contract what to do with it.

### What can be read?

Because the state variable is declared `public`, Solidity generates a getter named `value()`. After deployment with `42` and then a successful call to `setValue(100)`, calling `value()` returns `100`.

A custom function like `checkvalue()` is not necessary if all it does is return `value`, though writing one can be useful as a learning exercise.

### Is the value permanent?

The constructor runs once; the value it initializes is not necessarily permanent. A normal state variable can be changed by a function that assigns to it. Solidity's `constant` and `immutable` variables are different tools for values that must not be changed in the ordinary way after initialization.

The four parts fit together like this:

```text
deployment argument
      ↓
constructor runs once
      ↓
state variable gets its starting value
      ↓
setter can update that state variable later
      ↓
getter reads the current value
```

---

## Connections

```text
SimpleStorage
  ├── constructor: initialization during deployment
  ├── state variable: current stored value
  ├── setter: function parameter + assignment
  ├── getter: read current state
  ├── function body: explicitly defines what happens to inputs
  └── state transitions: value changes over time
```

Related ideas:
- [Mapping keys and values](./simple-storage-mapping-access.md) — contrasts per-address mapping storage with this exercise's single shared value.
- [Knowledge Map](../MAP.md) — connects this note to storage and state transitions.

---

## Current understanding

The constructor sets the **starting** value; it does not automatically make an ordinary state variable unchangeable. The state variable holds the **current** value. A setter must explicitly assign a new input to that variable, and a getter reads what is stored now.
