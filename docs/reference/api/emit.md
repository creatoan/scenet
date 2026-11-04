# Emitting

Panel Core to SVG, and to the exports for image models (#72). No emitter makes a layout
decision: everything it draws or says was already decided. The shapes Panel Core names but
does not spell out -- a burst's spikes, a tail's corners, where each letter lands -- are worked
out once in `scenet.emit.geometry`, and the order a panel is painted in is `scenet.emit.marks`,
so that every emitter draws the same thing (#80).

## `scenet.emit.svg`

```{automodule} scenet.emit.svg
```

## `scenet.emit.geometry`

```{automodule} scenet.emit.geometry
```

## `scenet.emit.marks`

```{automodule} scenet.emit.marks
```

## `scenet.emit.debug_svg`

```{automodule} scenet.emit.debug_svg
```

## `scenet.emit.strip`

```{automodule} scenet.emit.strip
```

## `scenet.emit.page`

```{automodule} scenet.emit.page
```

## `scenet.emit.conditioning`

```{automodule} scenet.emit.conditioning
```

## `scenet.emit.pose`

```{automodule} scenet.emit.pose
```

## `scenet.emit.boxes`

```{automodule} scenet.emit.boxes
```

## `scenet.emit.semantics`

```{automodule} scenet.emit.semantics
```

## `scenet.emit.depth`

```{automodule} scenet.emit.depth
```

## `scenet.emit.mask`

```{automodule} scenet.emit.mask
```

## `scenet.emit.export`

```{automodule} scenet.emit.export
```
