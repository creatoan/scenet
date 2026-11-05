# sRGB2014.icc

The International Color Consortium's sRGB profile (IEC 61966-2-1), ICC version 2, as published at
[color.org](https://www.color.org/srgbprofiles.xalter), unaltered. SHA-256
`384b832de3412066743b52a75ee906b6fb9fb8d9e09e936fc2c43223815c6e0a`.

The print PDF tags every RGB picture with it, written once per file, so a print workflow reads
the picture as the sRGB every browser reads it as (#283). `scripts/make_palette.py` converts the
tinted palette from it (#280).

In the International Color Consortium's terms:

> This profile is made available by the International Color Consortium, and may be copied,
> distributed, embedded, made, used, and sold without restriction. Altered versions of this
> profile shall have the original identification and copyright information removed and shall
> not be misrepresented as the original profile.
