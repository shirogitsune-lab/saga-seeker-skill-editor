# Match JSON and HTML entries by position

Skill and personality IDs cannot safely identify visual rows because valid IDs may be arbitrary, empty, or duplicated in existing sheets. The editor maps each JSON array item to the direct-child `li` at the same index and uses ID, name, type, description, and catalog data only as supporting validation. Descendant `li` elements never count as slots.

## Consequences

- A correspondence that cannot be established confidently becomes read-only.
- Skills may have trailing plain HTML slots without JSON objects; those positions are vacant skill slots.
- Personality keywords require exactly six direct-child HTML slots.
- Insertions, removals, and reordering must preserve ordered correspondence.
- Changing to ID-based matching would require revisiting this decision and the real-sheet compatibility tests.
