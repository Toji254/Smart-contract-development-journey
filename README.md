# Smart Contract Development Journey

> **A hands-on Solidity learning lab focused on understanding contracts deeply enough to test them, interact with them, break their assumptions, and explain the failures.**

**portfolio:** 4 progressively harder builds — eth accounting → multi-party state machines → erc20/erc721 interaction → interconnected bounty protocol.

**tags:** `sol | evm | foundry | sc | security | learning`

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

## Knowledge Web

This repository now has a living **[Solidity Knowledge Web](knowledge/README.md)** alongside the projects.

It is where I record the things I actually learned while building — especially the concepts that were confusing until they finally clicked.

~~~text
question / confusion
        ↓
build / investigate
        ↓
explanation
        ↓
my own words
        ↓
project connection
        ↓
later discovery
        ↓
connected knowledge map
~~~

Say **`study`** or **`anchor`** during a Solidity discussion to mark something for the knowledge layer.

The notes are deliberately not polished into a textbook:

- my own explanations stay in my own words
- the full explanation stays intact
- mistakes are kept as part of the learning history
- new discoveries are linked instead of silently replacing old ones

**[Open the Knowledge Map →](knowledge/MAP.md)**

## Why I am learning Solidity in the AI era

AI is already good enough to write large amounts of Solidity, generate tests, investigate code, and perform useful parts of a smart-contract audit. I am not learning Solidity because I believe humans will keep manually writing every line of blockchain code.

I already know how to use AI as a serious building tool. I have practical experience with AI-assisted development and have evidence that I can ship working projects with it. **This repository is not an attempt to learn how to vibe-code.**

I am learning Solidity because I want to understand what the AI is building.

The long-term goal is **AI-assisted smart-contract security**, not competing with AI at typing Solidity.

~~~text
AI can generate code
        ↓
I understand the code
        ↓
I understand the EVM behavior
        ↓
I can test the assumptions
        ↓
I can attack the contract
        ↓
I can verify whether an AI finding is real
        ↓
I can discover what the AI missed
~~~

That distinction matters. A model can report that a function "looks vulnerable," but security work requires knowing whether the alleged exploit is actually possible, what state transitions are involved, which assumptions are supposed to hold, and how different contracts interact.

So the projects in this repository are deliberate training grounds.

I am building them to learn:

- how Solidity actually behaves
- how storage, state, calls, and assets move through contracts
- how to reason about contract invariants and assumptions
- how to test normal behavior and failure cases
- how to manually interact with deployed contracts
- how to think like an attacker
- how to turn an observed weakness into a reproducible proof
- how to use AI and security tooling without becoming dependent on their answers

The projects are therefore **not the destination**. They are controlled environments for building the mental model needed to audit and reason about real protocols.

The objective is not to become the best Solidity code typist.

The objective is to become someone who can take an unfamiliar contract, understand what it is supposed to do, use AI and tooling to move faster, and still independently determine whether the system is actually safe.

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
| [MarkTrail](MarkTrail/README.md) | 5 | Real-world academic records system + Solidity audit layer |

That progression is intentional:

~~~text
single-contract ETH accounting
            ↓
multi-party state machine
            ↓
cross-contract token interaction
            ↓
full interconnected protocol
            ↓
real-world academic records system
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

**Build. Break. Explain. Rebuild. Use AI, but understand what it gives you.**

The finish line is not “I finished four projects.”

The finish line is:

> Give me a plain-English smart-contract requirement and I can design the state, write or direct the implementation, test it, interact with it, and start looking for ways it can fail — while using AI to make me faster, not to replace my understanding.

That is what this repository is meant to document.
