# Classify skills and repair IDs conservatively

The editor classifies a position in this order: JSON/HTML mismatch, explicit empty skill, default skill, original skill, then unknown. An original skill requires a non-empty textual name, textual description, and empty or absent type and key; its ID format is unrestricted. Existing arbitrary IDs are preserved, while an edited original with a non-textual, empty, or exactly duplicated ID requires explicit repair consent.

## Consequences

- Existing AI-generated IDs, Japanese IDs, and IDs containing symbols remain valid.
- Pre-existing empty or duplicate IDs remain byte-for-byte unchanged when their skills are not edited.
- New, repaired, and default-replacement originals receive the first unused positive `skN`.
- Default replacement is an advanced destructive operation with two confirmations because the old ID, type, and key are discarded.
- Unrecognized field combinations are displayed read-only rather than coerced into an original skill.
