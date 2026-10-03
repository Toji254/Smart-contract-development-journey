# Smart Contract Development Journey

This repository is a hands-on Solidity learning journey.

The goal is not to collect finished contracts. The goal is to document the process of going from a plain-English requirement to a working contract, tests, manual interaction, adversarial testing, and finally a comparison with the older implementation.

~~~text
plain-English problem
        ↓
design
        ↓
Solidity implementation
        ↓
Foundry tests
        ↓
manual interaction
        ↓
break it
        ↓
understand why it broke
        ↓
improve the design
~~~

## The rule

Do not start by reading the old contract.

Start with the project README. Treat it as the specification and learning path. The existing Solidity files are historical work that you inspect after attempting the exercise yourself.

~~~text
BAD LOOP
open old contract → read code → copy patterns → feel familiar

LEARNING LOOP
read problem → design → build → test → interact → break → compare
~~~

## Prerequisites

You do not need a complete professional Solidity background. You need basic programming knowledge, a terminal, Git, Foundry, and the willingness to investigate compiler errors instead of immediately copying a fix.

~~~bash
forge --version
cast --version
anvil --version
~~~

## Starting from scratch

The repository already contains Foundry project directories, so the exercise does not mean deleting the whole project folder. It means treating the contract logic and tests as a fresh build.

For a completely new Foundry project, the general setup is:

~~~bash
mkdir my-project
cd my-project
forge init
~~~

Then:

~~~text
src/        Solidity contracts
test/       Solidity tests
script/     deployment / interaction scripts
lib/        dependencies
foundry.toml
~~~

## The rebuild loop

### 1. Read the problem

Answer these before coding:

- Who are the actors?
- What can each actor do?
- What assets move?
- What state must be remembered?
- Who is allowed to change that state?
- What must never happen?

### 2. Draw the flow

~~~text
caller
  ↓
function
  ↓
checks
  ↓
state change
  ↓
asset movement
  ↓
event
~~~

### 3. Design the data

Every storage variable should answer a real question the contract needs to remember.

### 4. Build the smallest complete path

Do not start with every stretch feature. Make one full path work first, then add the next state transition.

### 5. Test valid behavior

Prove the happy path.

### 6. Test invalid behavior

Test wrong callers, wrong states, zero values, repeated actions, failed external calls, and accounting edge cases.

### 7. Interact manually

Use Anvil plus Cast or a small Foundry script. Watch actual state and balance changes rather than only reading test assertions.

### 8. Break it

Become the attacker. Try to violate the rules you wrote down.

### 9. Compare with history

Only now inspect the old implementation and ask what you understood now that you did not understand when you first wrote it.

## Projects

| Project | Order | Main lesson |
| --- | --- | --- |
| [Tipjar](Tipjar%20project/README.md) | 1 | ETH accounting and ownership |
| [ETH Escrow](ETH%20Escrow/README.md) | 2 | Multi-party state machines |
| [Purchase NFT with ERC20 Tokens](Purchase%20NFT%20with%20ERC20%20tokens/README.md) | 3 | ERC20 + ERC721 interaction |
| [BountyArena](Bounty%20Arena/README.md) | 4 | Interconnected protocol design |

That progression is intentional:

~~~text
single-contract ETH accounting
            ↓
multi-party state machine
            ↓
cross-contract token interaction
            ↓
full interconnected protocol
~~~

## Standard checkpoints

1. Understand the problem.
2. Design the state and data model.
3. Implement the first valid flow.
4. Read the resulting state.
5. Test valid behavior.
6. Test invalid behavior.
7. Interact manually.
8. Attack the assumptions.
9. Compare with the historical implementation.
10. Record what you learned.

## Tooling

~~~bash
forge build
forge test
forge test -vv
forge fmt
~~~

Start a local chain with Anvil when you want to interact manually.

~~~bash
anvil
~~~

Use security tooling after you understand the basic behavior. Static analysis gives you signals; your job is to understand what the signal means.

## Repository philosophy

Build. Break. Explain. Rebuild.

The finish line is not “I finished four projects.”

The finish line is:

> Give me a plain-English smart-contract requirement and I can design the state, write the contract, test it, interact with it, and start looking for ways it can fail.

That is what this repository is meant to document.