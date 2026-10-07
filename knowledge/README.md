# Solidity Knowledge Web

This is the **living knowledge layer** of the Smart Contract Development Journey.

The projects are where I build and break things.

This folder is where I keep the things I actually learned, the things I originally misunderstood, the explanations that finally made something click, and the connections between all of them.

## The capture rule

When I say **`study`** or **`anchor`** during a Solidity discussion, capture the lesson from that discussion here.

The capture should contain:

1. **My understanding** — my own words exactly as I said them.
2. **The explanation** — the full explanation given in the conversation, not a shortened summary.
3. **Connections** — links to the concepts, projects, syntax, or security ideas this lesson touches.
4. **What changed** — later discoveries or corrections stay visible instead of silently replacing the old understanding.

### Important rule about my wording

When I explain something in my own words, **do not rewrite it into technical language**.

My imperfect wording is part of the learning history.

Do not clean it up just because a more technically correct sentence exists. Keep my version, then put the more precise explanation beside it.

That makes this repository a record of how my understanding developed, not a polished textbook pretending I knew everything from the start.

## The web

Start here:

**[Open the Knowledge Map](MAP.md)**

The map connects:

~~~text
projects
   ↕
concepts
   ↕
Solidity syntax
   ↕
EVM behaviour
   ↕
security assumptions
   ↕
mistakes / discoveries
~~~

The same concept can appear in several projects. A note should therefore link back to the projects where that concept became real.

## Project connections

| Project | What it currently connects to |
| --- | --- |
| [Tipjar](../Tipjar%20project/README.md) | ETH, balances, ownership, calls |
| [ETH Escrow](../ETH%20Escrow/README.md) | actors, state transitions, ETH accounting |
| [Purchase NFT with ERC20 Tokens](../Purchase%20NFT%20with%20ERC20%20tokens/README.md) | interfaces, ERC20, ERC721, `transferFrom`, allowances, inheritance |
| [BountyArena](../Bounty%20Arena/README.md) | structs, mappings, enums, IDs, ownership, interconnected state |

These are starting connections. New study notes should make the map richer as the journey continues.

## How notes grow

A note starts from the moment something was confusing, then records what made it click.

~~~text
confusion
   ↓
question
   ↓
explanation
   ↓
my own words
   ↓
project where I used it
   ↓
later discovery / correction
   ↓
new connections
~~~

The point is not to produce perfect notes.

The point is to make it possible to open the repository months later and trace **why I understand something now**.
