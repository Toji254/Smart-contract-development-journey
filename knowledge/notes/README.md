# Study Notes

This is the note index.

Notes are added when I use the trigger **`Add`** (case-insensitive), or when I explicitly ask for a knowledge-web capture.

## Rules for every note

### My words stay my words

When I explain an idea myself, that wording is kept exactly as I gave it.

No polishing.
No translating it into auditor-speak.
No replacing it with a textbook definition.

A precise explanation can sit beside it, but my version stays.

### The explanation stays complete

When a lesson is captured, the assistant explanation is stored in full rather than reduced to a few bullet points.

### Corrections stay visible

If I later discover that my understanding was wrong or incomplete, the old wording is not deleted.

Instead:

~~~text
what I thought
      ↓
what I discovered
      ↓
what I understand now
~~~

That makes the progression useful for revision and auditing my own reasoning.

### Connections are links

Notes should link to:

- related notes
- the project or exercise where the idea appeared
- other Solidity concepts it depends on
- security ideas that use the concept

## Note template

Use **[NOTE TEMPLATE](../_NOTE_TEMPLATE.md)** when creating a new entry.

## Captured notes

- [SimpleStorage refresher: mapping keys and values](./simple-storage-mapping-access.md) — the difference between a mapping's name, key type, mapped-value name, and a concrete lookup such as `value[msg.sender]`; includes the original syntax mistake and the full explanation.
- [SimpleStorage refresher: constructor, state variable, setter, and getter](./simple-storage-constructor-setter-getter.md) — why the constructor sets the starting value rather than freezing it, how a setter explicitly updates state, and how a getter reads the current value.
- [Solidity visibility and automatic getters](./solidity-visibility-and-automatic-getters.md) — what can be `public`, the difference between public state variables and public functions, local variables/parameters, and mapping/array getter calls.
