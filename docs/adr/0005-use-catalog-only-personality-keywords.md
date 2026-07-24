# Use catalog-only personality keywords

Personality keywords are game-defined records rather than user-authored text. The editor accepts only entries that exactly match the bundled catalog across ID, name, system, and karma, and it does not provide original personality keyword creation. A valid character selection contains at most six unique catalog entries packed from the first slot without gaps.

## Consequences

- Search, filters, drag and drop, and reorder controls change selection ergonomics but not catalog validation.
- Unknown, partially matching, duplicated, or sparse personality data becomes read-only or blocks saving.
- Editing preserves unchanged personality objects and HTML slots as bytes.
- Catalog changes require validation of all four fields and real-sheet compatibility, not only ID/name updates.
