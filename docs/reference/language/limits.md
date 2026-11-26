# Limits (normative)

Every size, count and length in the language has an upper bound. Without one, a single line
could make the compiler work without end: rain over a panel a million units wide was a hundred
million streaks. The limits are generous for real comics -- nothing in the gallery comes within
half of one -- and a document past one is refused before anything is compiled, with the finding
[`limit`](../diagnostics.md#limit) at the value, which says the limit and the value past it.

A panel unit is a tenth of a millimetre printed, so a panel of 10 000 units is a metre wide.

| Limit | Value | What it bounds |
|---|---|---|
| `panel_side` | 10 000 | A panel's width or height, in panel units |
| `page_side` | 10 000 | A page's width or height, in panel units |
| `panels_per_page` | 200 | The panels one page lays out, insets included |
| `pages_per_document` | 1 000 | The pages one document lays out |
| `panels_per_document` | 10 000 | The panels one document holds |
| `actors_per_panel` | 50 | The cast members of one panel |
| `events_per_panel` | 100 | The lines, captions and sounds of one panel's script |
| `characters_per_text` | 2 000 | The characters of one line, caption, sound or description |
| `image_bytes` | 134 217 728 | The bytes of a supplied picture's file, 128 MiB |
| `image_pixels` | 200 000 000 | The pixels of a supplied picture, its width times its height |
| `font_bytes` | 67 108 864 | The bytes of a font file, 64 MiB |
| `document_bytes` | 8 388 608 | The bytes of a document in UTF-8, and of a puppet file or an artwork contract, 8 MiB |

An identifier, an actor id or a panel name, is at most 64 characters; see
[identifiers](identifiers.md).

A file is refused by its size before a byte of it is read: a picture, a font, a puppet file or an
artwork contract larger than its bound is a finding of the file's own rule (`image-file`,
`font-file`, `puppet-file`, `artwork-contract`), at the key that names it, and a document file
larger than `document_bytes` is not read at all. Those bounds are also
`scenet.limits.DOCUMENT_BYTES`, `IMAGE_BYTES` and `FONT_BYTES`, read at each read, so a host can
lower them before it compiles. A document given as text, not as a file, is a `limit` finding.

The JSON Schemas state the limits they can -- a panel's size, the length of a text, the size of a
cast, a script, the panels and the pages -- so an editor and a model see them too. The others, the
panels on a page and the files a document names, `scenet check` finds.

## Tighter limits

`scenet.limits.Limits` holds them, and `scenet.limits.LIMITS` is the language's. A host that
compiles documents it does not trust may hold them to less: a `Limits` with any value lowered, but
none raised, which `scenet.mcp.build_server(limits=...)` takes for every request.
