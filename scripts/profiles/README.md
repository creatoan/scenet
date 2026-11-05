# ICC profiles for the print palette

`scripts/make_palette.py` converts the tinted palette's colours to CMYK, and measures black's
ramp, through two profiles (#280). The printing condition's is here, read by the script and its
tests only: it is not in the package, and print converts nothing at run time. The source,
`sRGB2014.icc`, is in the package, `src/scenet/profiles/`, since print tags RGB pictures with it
(#283); its README gives its source, digest and licence. Both are committed as they were
published, unaltered.

| File | What it is | From | SHA-256 |
|---|---|---|---|
| `GRACoL2013_CRPC6.icc` | CGATS21-2-CRPC6, GRACoL 2013 coated #1, ICC version 4 | ICC registry, [GRACoL2013_CRPC6](https://registry.color.org/profile-registry/GRACoL2013_CRPC6), by IDEAlliance with X-Rite | `4ebbfad6bc9cfc033fdafdd8ac5df8159208932cb16d9a6596d349ae7ab50443` |

## Licences

`GRACoL2013_CRPC6.icc`, as its own copyright tag says:

> Copyright X-Rite, Inc. This profile is made available by IDEAlliance, with permission of
> X-Rite, Inc., and may be used, embedded, exchanged, included in commercial software and shared
> without restriction. It may not be altered without written permission of IDEAlliance except
> for single site use.
