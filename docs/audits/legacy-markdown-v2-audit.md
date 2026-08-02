# Anonymous legacy Markdown audit for AI-oriented Markdown format v2

Date: 2026-07-31

This read-only audit rechecked 163 Markdown files produced by the earlier
standalone conversion workflow. It recorded only aggregate format,
warning/error codes, and source hashes. It did not retain file names,
character names, prose, or paths.

## Results

- Files: 163
- Lexical format: 163 `LEGACY_UNMARKED`
- Normal parse before consent: 163 refused
- Parse after explicit `allow_legacy=True`: 161 creatable, 2 blocked
- Blocking errors: one `duplicate-profile-field`, one `too-many-skills`
- Source hashes after audit: all unchanged

Aggregate warnings:

| Code | Count |
| --- | ---: |
| `legacy-empty-marker` | 10 |
| `legacy-image-not-restored` | 163 |
| `legacy-memories-not-restored` | 163 |
| `legacy-missing-personality` | 7 |
| `legacy-missing-profile` | 14 |
| `legacy-missing-status` | 12 |
| `profile-length` | 1 |

Missing values remain warnings because their fallback is deterministic.
Duplicate recognized structure and over-limit skills remain errors because the
requested import cannot be accepted without changing meaning or limits.
