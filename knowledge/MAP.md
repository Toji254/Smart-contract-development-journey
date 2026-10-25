# Knowledge Map

This page is the visual index of the Solidity learning journey.

GitHub renders the Mermaid diagram below, so the repository itself acts like a small connected knowledge web.

## Current map

~~~mermaid
flowchart TD
    J["Smart Contract Journey"] --> T["Tipjar"]
    J --> E["ETH Escrow"]
    J --> P["Purchase NFT with ERC20"]
    J --> B["BountyArena"]
    J --> S["SimpleStorage refresher"]

    T --> ETH["ETH / msg.value / balances"]
    T --> OWN["Ownership / privileged actions"]

    E --> ACT["Actors"]
    E --> STATE["State transitions"]
    E --> ETH

    P --> INT["Interfaces"]
    P --> ERC20["ERC20"]
    P --> ERC721["ERC721"]
    P --> TF["transferFrom"]
    P --> ALLOW["Allowances"]
    P --> INH["Inheritance"]

    B --> STRUCT["Structs"]
    B --> MAP["Mappings"]
    B --> ENUM["Enums"]
    B --> ID["IDs / keccak256"]
    B --> OWN
    B --> ETH

    S --> MAP
    S --> KEY["Mapping key type: address"]
    S --> VAL["Mapped value: uint256"]
    S --> LOOKUP["Mapping access: value[key]"]
    S --> CALLER["msg.sender"]
    S --> CHECK["checkvalue() / returns uint256"]
    S --> DEFAULT["Default uint256 value: 0"]
    S --> INIT["Constructor: starting value"]
    S --> SVAR["State variable: current value"]
    S --> SETTER["Setter: changes current value"]
    S --> GETTER["Getter: reads current value"]
    S --> BODY["Function body executes instructions"]
    S --> VIS["Visibility: public / external / internal / private"]
    S --> AUTOGET["Public state variable: automatic getter"]
    S --> PUBLICFN["Public function: externally and internally callable"]
    S --> LOCAL["Local variables and parameters: no visibility setting"]
    S --> MAPGET["Public mapping/array getter: one key or index"]
    S --> VISCHEAT["Visibility and getters cheatsheet"]
    S --> GETWHEN["When to use a getter: inside vs outside"]

    KEY --> LOOKUP
    VAL --> LOOKUP
    CALLER --> LOOKUP
    CHECK --> LOOKUP
    LOOKUP --> STORAGE
    DEFAULT --> LOOKUP

    INIT --> SVAR
    SETTER --> BODY
    BODY --> ASSIGN["Assignment: value = _value"]
    PARAM["Function parameter receives input"] --> ASSIGN
    ASSIGN --> SVAR
    SVAR --> GETTER
    SVAR --> AUTOGET
    AUTOGET --> GETTER
    PUBLICFN --> VIS
    LOCAL --> BODY
    MAPGET --> AUTOGET
    VISCHEAT --> VIS
    VISCHEAT --> AUTOGET
    GETWHEN --> GETTER
    GETWHEN --> SVAR
    VIS --> GETTER
    SVAR --> STORAGE

    INT --> CALL["Calling a function through a contract/interface"]
    ERC20 --> TF
    ALLOW --> TF
    INH --> CALL

    CALL --> EVM["EVM behaviour"]
    STATE --> EVM
    MAP --> STORAGE["Storage"]
    STRUCT --> STORAGE

    EVM --> SEC["Security reasoning"]
    STORAGE --> SEC
    ETH --> SEC
    TF --> SEC

    SEC --> DISC["Discoveries / mistakes / attack ideas"]

    classDef project fill:#eef2ff,stroke:#4f46e5,color:#111827;
    classDef concept fill:#ecfeff,stroke:#0891b2,color:#111827;
    classDef security fill:#fff7ed,stroke:#ea580c,color:#111827;

    class T,E,P,B,S project;
    class ETH,OWN,ACT,STATE,INT,ERC20,ERC721,TF,ALLOW,INH,STRUCT,MAP,ENUM,ID,CALL,EVM,STORAGE,KEY,VAL,LOOKUP,CALLER,CHECK,DEFAULT,INIT,SVAR,SETTER,GETTER,BODY,ASSIGN,PARAM,VIS,AUTOGET,PUBLICFN,LOCAL,MAPGET,VISCHEAT,GETWHEN concept;
    class SEC,DISC security;
~~~

New captures:
- [SimpleStorage refresher — mapping keys, values, and caller-based lookup](notes/simple-storage-mapping-access.md).
- [SimpleStorage refresher — constructor, state variable, setter, and getter](notes/simple-storage-constructor-setter-getter.md).
- [Solidity visibility and automatic getters](notes/solidity-visibility-and-automatic-getters.md).
- [Solidity visibility and getters cheatsheet](notes/solidity-visibility-getters-cheatsheet.md).
- [When to use a getter](notes/when-to-use-a-getter.md).

## How to read it

A line means **these ideas are connected**, not that one idea automatically causes the other.

For example:

`IERC20` is connected to `transferFrom`, because using an ERC20 interface is one way a contract can call the token contract's `transferFrom` function.

That concept is then connected to allowances, because ERC20 `transferFrom` normally depends on an allowance being available.

The actual study notes sit behind these concepts as they are captured.

## Notes index

Go to **[all captured notes](notes/README.md)**.

Every note should link back to this map and to the project where the idea became useful.

## Note types

~~~text
concept       → a Solidity / EVM idea
syntax        → something about how Solidity is written
project       → something learned while building a project
security      → a security assumption, weakness, or attack idea
discovery     → something I figured out myself
mistake       → something I got wrong and later understood
tooling       → something learned about Foundry / Cast / Anvil / audit workflow
~~~

One note can have more than one connection.
