# Emitting

Panel Core to SVG, to a print PDF, and to the exports for image models. No emitter makes a layout
decision: everything it draws or says was already decided. The shapes Panel Core names but
does not spell out -- a burst's spikes, a tail's corners, where each letter lands -- are worked
out once in `scenet.emit.geometry`, and the order a panel is painted in is `scenet.emit.marks`,
so that every emitter draws the same thing.

## `scenet.emit.svg`

```{eval-rst}
.. automodule:: scenet.emit.svg
```

## `scenet.emit.geometry`

```{eval-rst}
.. automodule:: scenet.emit.geometry
```

## `scenet.emit.marks`

```{eval-rst}
.. automodule:: scenet.emit.marks
```

## `scenet.emit.pdf`

```{eval-rst}
.. automodule:: scenet.emit.pdf
```

## `scenet.emit.pdf_fonts`

```{eval-rst}
.. automodule:: scenet.emit.pdf_fonts
```

## `scenet.emit.pdf_images`

```{eval-rst}
.. automodule:: scenet.emit.pdf_images
```

## `scenet.emit.turbulence`

```{eval-rst}
.. automodule:: scenet.emit.turbulence
```

## `scenet.emit.cmyk`

```{eval-rst}
.. automodule:: scenet.emit.cmyk
```

## `scenet.emit.debug_svg`

```{eval-rst}
.. automodule:: scenet.emit.debug_svg
```

## `scenet.emit.strip`

```{eval-rst}
.. automodule:: scenet.emit.strip
```

## `scenet.emit.page`

```{eval-rst}
.. automodule:: scenet.emit.page
```

## `scenet.emit.conditioning`

```{eval-rst}
.. automodule:: scenet.emit.conditioning
```

## `scenet.emit.pose`

```{eval-rst}
.. automodule:: scenet.emit.pose
```

## `scenet.emit.boxes`

```{eval-rst}
.. automodule:: scenet.emit.boxes
```

## `scenet.emit.semantics`

```{eval-rst}
.. automodule:: scenet.emit.semantics
```

## `scenet.emit.depth`

```{eval-rst}
.. automodule:: scenet.emit.depth
```

## `scenet.emit.mask`

```{eval-rst}
.. automodule:: scenet.emit.mask
```

## `scenet.emit.export`

```{eval-rst}
.. automodule:: scenet.emit.export
```

## `scenet.emit.preview`

```{eval-rst}
.. automodule:: scenet.emit.preview
```
