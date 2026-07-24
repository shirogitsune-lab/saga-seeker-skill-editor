# Preserve source bytes with targeted patches

Character sheets can contain large embedded images, personal settings, unknown fields, and formatting that the editor does not own. The editor therefore keeps the input as bytes and replaces only the intended JSON string tokens or one intended object plus its corresponding HTML element. It does not reserialize an entire data array or normalize the document, and it rejects unexpected target structure instead of reconstructing it.

## Consequences

- Unedited objects, unknown fields, attributes, whitespace, and surrounding HTML remain byte-for-byte unchanged.
- Existing newline style is retained around each edited JSON or HTML region.
- Every new edit operation needs explicit replacement ranges, round-trip validation, and unchanged-segment tests.
- Broader reformatting or HTML parser serialization is incompatible with this decision.
