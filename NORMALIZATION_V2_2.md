# V2.2 normalization update

Derived from R33 V2.1; original images and raw references/predictions remain unchanged.

- Ellipsis runs (3+ points, including … / ⋯) collapse to one `…`; 1–2 baseline or centered points retain the previous distinction.
- Repeated prolonged marks collapse to `ー`; wave aliases and runs collapse to `〜`.
- Preserve へ/ヘ, べ/ベ, ぺ/ペ distinctions, including after halfwidth kana expansion.
- Preserve `ー`, em dash `—`, horizontal bar `―`, minus `−`, hyphen `-`, and box drawing `─` separately. Vertical em dash `︱` and small em dash `﹘` map to `—`, never to `ー`.
- En dash `–` and figure dash `‒` stay separate; vertical en dash `︲` maps to `–`. Hyphen variants retain their mapping to `-`; halfwidth prolonged mark `ｰ` maps to `ー`.

The original R33 V2.1 release is preserved separately. Historical README tables and release hashes describe that original release; use newly rescored V2.2 reports for this policy. No producer or training dictionary is silently changed by this evaluation update.
