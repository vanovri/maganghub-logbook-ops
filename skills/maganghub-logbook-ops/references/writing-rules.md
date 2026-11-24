# Writing Rules for the MagangHub Daily Report

Adapted with attribution from `raditsoic/maganghub-autofill` (MIT). Rule framing is English; report examples are Indonesian.

| Group | Rules |
|---|---|
| Facts | `W-01` facts only from evidence, `W-02` real struggles only, `W-03` lessons follow activities |
| Perspective | `W-10` no person perspective (`saya/aku/kami/kita/penulis/Anda`), `W-11` active `meN-` verbs in bullets (no `di-` passive) |
| Language | `W-20` standard Indonesian + original technical terms, `W-21` no empty vocabulary, `W-22` no em dash/theatrical openers, `W-23` no hyperbole |
| Structure | `W-30` 3-5 activity bullets (`- `), `W-31` one paragraph each for lessons & struggles, `W-32` 100-5000 chars per part, `W-33` outline outcomes only |
| Safety | `W-40` no secrets, credentials, internal URLs/IPs, confidential client names, or PII |
| Form text | `W-50` report content only (no `[INFERENCE]`, `Catatan:`, `Perlu konfirmasi`, greetings, or closers) |

## Key Requirements

- **Uraian aktivitas (`aktivitas`)**: 3-5 bullet lines starting with `- `, each opening with an active `meN-` verb (`Membuat`, `Menyusun`, `Memeriksa`, `Menguji`), summarizing major outcomes rather than small git/typo steps.
- **Pembelajaran yang diperoleh (`pelajaran`)**: One single paragraph (2-4 sentences, no bullets, no line breaks), >= 100 characters, directly tied to the day's activities.
- **Kendala yang dialami (`kendala`)**: One single paragraph (2-4 sentences, no bullets, no line breaks), >= 100 characters, describing real blockers or an honest confirmation of zero notable technical blockers when confirmed by the user.
- **Safety & Accuracy**: Never invent numbers, metrics, or incidents. Never include secrets, personal contact details, or confidential client names.
