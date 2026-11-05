# ICC profiles for the print palette

`scripts/make_palette.py` converts the tinted palette's colours to CMYK, and measures black's
ramp, through these two profiles (#280). They are read by the script and its tests only: neither
is in the package, and print converts nothing at run time. Both are committed as they were
published, unaltered.

| File | What it is | From | SHA-256 |
|---|---|---|---|
| `sRGB2014.icc` | sRGB (IEC 61966-2-1), ICC version 2 | International Color Consortium, [color.org](https://www.color.org/srgbprofiles.xalter) | `384b832de3412066743b52a75ee906b6fb9fb8d9e09e936fc2c43223815c6e0a` |
| `GRACoL2013_CRPC6.icc` | CGATS21-2-CRPC6, GRACoL 2013 coated #1, ICC version 4 | ICC registry, [GRACoL2013_CRPC6](https://registry.color.org/profile-registry/GRACoL2013_CRPC6), by IDEAlliance with X-Rite | `4ebbfad6bc9cfc033fdafdd8ac5df8159208932cb16d9a6596d349ae7ab50443` |

## Licences

`sRGB2014.icc`, in the International Color Consortium's terms:

> This profile is made available by the International Color Consortium, and may be copied,
> distributed, embedded, made, used, and sold without restriction. Altered versions of this
> profile shall have the original identification and copyright information removed and shall
> not be misrepresented as the original profile.

`GRACoL2013_CRPC6.icc`, as its own copyright tag says:

> Copyright X-Rite, Inc. This profile is made available by IDEAlliance, with permission of
> X-Rite, Inc., and may be used, embedded, exchanged, included in commercial software and shared
> without restriction. It may not be altered without written permission of IDEAlliance except
> for single site use.
