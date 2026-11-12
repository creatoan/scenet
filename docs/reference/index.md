# Language and tools

The reference for whoever writes comics in Scenet: the language, key by key, and the tools that
read it. Nothing here teaches; for that, start with the [tutorial](../tutorial/index) or a
[how-to guide](../howto/index). The Python API has [a reference of its own](api/index.md).

## The language

| | |
|---|---|
| [Language specification](language/index.md) | Every block and key of the language, a card each, with examples |
| [All keys, A to Z](language/keys.md) | Every key in one table, with its meaning and the release it appeared in |
| [Glossary](glossary.md) | The words the reference uses |
| [Shot types](shot_types.md) | **Normative.** What each shot type means, in head-heights |
| [Panel Core](panel_core.md) | The resolved intermediate format |
| [Asset contract](asset_contract.md) | What a character puppet must declare |

The language specification is what a second implementation would target, and it is
[free to implement](../explanation/why.md#free-to-implement).

## The tools

| | |
|---|---|
| [Command line](cli.md) | Every command and flag |
| [Diagnostics](diagnostics.md) | Every rule `scenet check` reports and every note the compiler gives, each with a document that gives it and the same document fixed |
| [MCP server](mcp.md) | The tools `scenet mcp` serves to a model |

## Versions

Every key's card, every command and option, and every diagnostic says the release it arrived in.
[What Scenet does today](../explanation/status.md) has the features as a whole, and
[What's new](../explanation/whats_new.md) what each release changed.

```{toctree}
:hidden:
:maxdepth: 2

language/index
glossary
shot_types
panel_core
asset_contract
cli
diagnostics
mcp
```
