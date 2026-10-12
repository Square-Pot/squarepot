# Label fonts

DejaVu Sans Condensed (regular, oblique and bold) from the
[DejaVu fonts 2.37 release](https://github.com/dejavu-fonts/dejavu-fonts/releases/tag/version_2_37)
(`dejavu-fonts-ttf-2.37.tar.bz2`, SHA-256
`fa9ca4d13871dd122f61258a80d01751d603b4d3ee14095d65453b4e846e17d7`), under the
license in [LICENSE](LICENSE).

The files are subset to Latin, Cyrillic and common punctuation, without hinting:

```sh
pyftsubset DejaVuSansCondensed.ttf \
  --unicodes='U+0020-007E,U+00A0-024F,U+0400-04FF,U+2010-2027,U+2030-203A,U+2116' \
  --layout-features='' --no-hinting --drop-tables+=DSIG
```

(fontTools 4.66.1; the same for the `-Oblique` and `-Bold` files.) Characters
outside the subset print as `?`.
