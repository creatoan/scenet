# The language

The intermediate representation: a validated semantic scene graph, and the real
definition of the language. Nothing here carries a coordinate.

## `scenet.ir`

```{automodule} scenet.ir
```

## `scenet.places`

The named-place library. A preset expands into a mass list an author could have written
themselves, which is what keeps it a library rather than a second, opaque format -- and
the expansion happens in the frontend, so nothing downstream ever sees a `place`.

```{automodule} scenet.places
```

## `scenet.emphasis`

How a stressed word is written: between underscores, by Markdown's rules for them. Used by
the IR to refuse emphasis that is never closed, and by the solver to decide which face each
character is measured and drawn in -- one function, so the two cannot disagree.

```{automodule} scenet.emphasis
```

## `scenet.lettering`

An author's lettering face: reading the font files a document declares, and what stands in
for a face it does not name.

```{automodule} scenet.lettering
```

## `scenet.paths`

Files a document names, found beside the document -- never by an absolute path.

```{automodule} scenet.paths
```
