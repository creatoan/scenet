# Scenet JSON

The language is one data model with two concrete syntaxes. [Scenet YAML](yaml_profile.md) is the
one people write by hand; **Scenet JSON** is the one programs and models write. Every document has
both forms -- a panel, a scene, a puppet file, an artwork contract -- and the two build the same
Core.

## Which documents are JSON

A document is read as JSON when its file ends in `.json` -- `story.scene.json`,
`hero.panel.json`, `pip.puppet.json`, `figures.art.json` -- or when its text opens a JSON
object: `{`, then a quoted key or `}`, past any white space. A YAML flow mapping, `{cast: ...}`,
quotes no key, so it is still YAML. `scenet build`, `scenet check`, the MCP tools and the Python
functions that take text all read either.

A cast member's `reference` may name a puppet file in JSON, `puppets/pip.puppet.json`, and a
supplied picture's artwork contract may be beside it in JSON, `p01.art.json`, when there is no
`p01.art.yaml`.

## The data model

JSON's own: an object, an array, a string, a number, `true`, `false` and `null`. It is the model
Scenet YAML reads into, so what a key means does not depend on the carrier:

- **A number is text as it was written** where the language expects text: `"text": 1.50` letters
  `1.50` in both carriers.
- **`null` is a key not written**, in a mapping, as in YAML: it leaves something out of a panel
  that would inherit it.
- **A key written twice in one object is refused**, as `duplicate-key`, at the second, with the
  line of the first. Most JSON readers keep the last without a word.
- **`$schema` at the top** names the schema an editor checks the document with, as in YAML; see
  [a document's own keys](document.md).
- **An `x-` key** is an [extension](document.md#extension-keys), ignored at any depth.

What JSON writes that YAML would refuse is read: a tab between tokens, an emoji escaped as two
surrogates (`"\ud83d\ude00"`, which `json.dumps` writes by default), a key of any length.

Every finding is located by line and column, as a YAML document's is.

## Converting

`scenet convert` writes a document in the other carrier, keys in the order written and every
number as it was; `--lists` writes `panels` and every `cast` as [lists](scene.md#panels), which no
tool that sorts keys can reorder. See [`scenet convert`](../cli.md#scenet-convert).

```{code-block} json
:caption: hello.panel.json

{
  "$schema": "https://creatoan.github.io/scenet/schemas/panel.schema.json",
  "cast": [
    {"id": "alice", "reference": "alice", "pose": "pointing", "at": "left_third"},
    {"id": "bob", "reference": "bob", "at": "right_third", "facing": "left"}
  ],
  "script": [{"say": {"by": "alice", "text": "There it is."}}]
}
```
