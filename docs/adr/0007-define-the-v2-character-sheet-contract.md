# Define the v2 character-sheet contract from the Phase 0 game round trip

On 2026-07-24, the game successfully imported and re-exported both Phase 0
application-authored sheets:

- a sheet containing the complete blank initial state; and
- a probe covering the name, all seven profile fields, six visible statuses,
  compatibility-only charm, an icon, a protected default skill, an original
  skill, vacant skill slots, a catalog personality keyword, normal memories,
  placeholder memories, and eight ordered memories.

The source candidates used for the manual check matched the generator outputs
byte-for-byte. Both re-exports retained the JSON schema, types, key order, array
order, profile values, status values, skills, personality keyword, memory
objects, placeholder positions, and the seventh and eighth memories. The game
showed no import error and completed both exports.

This result promotes the Phase 0 candidate produced by
`build_candidate_golden_document` to the definitive v2 new-sheet JSON
contract. The generated Phase 0 HTML and game re-exports remain private
validation artifacts and are not repository fixtures.

## Definitive golden JSON

The complete initial object has this fixed key order and these initial values:

```json
{
  "formatVersion": "1.0.0",
  "exportedAt": "YYYY-MM-DDTHH:mm:ss.ffffff0Z",
  "data": {
    "characterId": "<uuid-v4-lowercase>_<YYYY-MM-DD>",
    "name": "",
    "profile": {
      "basicSettings": "",
      "appearance": "",
      "personality": "",
      "speechStyle": "",
      "background": "",
      "talentsAndRole": "",
      "otherFeatures": ""
    },
    "status": {
      "strength": "E",
      "endurance": "E",
      "intelligence": "E",
      "mentalStrength": "E",
      "agility": "E",
      "charm": "E",
      "luck": "E"
    },
    "skills": [],
    "personalities": [],
    "memories": [],
    "icon": {
      "mime": "image/webp",
      "dataUri": "data:image/webp;base64,<default-icon-base64>"
    }
  }
}
```

`<default-icon-base64>` denotes the complete Base64 encoding of the
application's default WebP bytes; it is not a literal saved value. The
authoritative construction is:

```python
"data:image/webp;base64," + base64.b64encode(default_icon_bytes).decode("ascii")
```

The serializer uses UTF-8 without BOM, LF line endings, two-space indentation,
the displayed key order, and `ensure_ascii=False`. UUID, clock, and local time
zone sources are injectable. `exportedAt` is the injected time converted to UTC
with six Python microsecond digits followed by a seventh `0`. Character IDs use
the injected local date.

The exact placeholder-memory object is:

```json
{
  "id": "",
  "title": "",
  "summary": "",
  "location": "",
  "intent": "",
  "outcome": "",
  "tags": [],
  "isPlaceholder": true
}
```

## Observed game normalization

The game does not produce a byte-preserving export of an imported sheet.
During both Phase 0 round trips it generated a new valid `characterId` and
`exportedAt`, rebuilt the presentation HTML, and re-encoded the 512 by 512 WebP
icon while retaining its MIME type and dimensions. The decoded test icon
remained visually equivalent. When the imported name was empty, the game
exported a non-empty name derived from the chosen export file name. A non-empty
probe name was retained exactly.

These transformations are game-export normalization, not changes to the
editor's preservation rules. Opening and saving an existing sheet in the
editor without an edit must still return the original bytes exactly.

## HTML contracts

There are two distinct HTML contracts.

### Application-authored import contract

The game import-critical element is exactly one:

```html
<script id="character-sheet-data" type="application/json">…</script>
```

The Phase 0 application-authored browser view also uses these unique IDs:

- `name-value`
- `profile-value`
- `abilities-value`
- `skills-value`
- `personality-value`
- `memories-value`
- `icon-value`

`profile-value` is an application view wrapper. It is deliberately not
required when loading a game-exported sheet.

### Game-export presentation contract

A game re-export contains the unique wrapper IDs `container`, `name`, `detail`,
`icon`, `personality`, `abilities`, `skills`, and `memories`, their
corresponding `*-value` IDs, and `character-sheet-data`. Profile fields are
direct `.tab-content[data-tab-key]` elements under `detail`; the game does not
emit `profile-value`.

The profile correspondence is:

| `data.profile` key | `data-tab-key` |
| --- | --- |
| `basicSettings` | `Basic Settings` |
| `appearance` | `Appearance` |
| `personality` | `Personality` |
| `speechStyle` | `Speaking Style` |
| `background` | `Background` |
| `talentsAndRole` | `Special Skills & Role` |
| `otherFeatures` | `Other Traits` |

Visible statuses map in order to `Strength`, `Endurance`, `Intelligence`,
`Willpower`, `Agility`, and `Luck`, and to JSON keys `strength`, `endurance`,
`intelligence`, `mentalStrength`, `agility`, and `luck`. The rank letters are
`E`, `D`, `C`, `B`, `A`, and `S`, represented by one through six active gauge
segments. `data.status.charm` is required compatibility data, is initialized to
`E`, and is not rendered or edited.

## Ordered list correspondence

JSON arrays remain the source of truth. Existing entries correspond to direct
child `li` elements by array position, never by ID.

### Skills

`ul#skills-value` contains six direct `li` slots. A displayed registered skill
uses:

- `data-skill-id` from `id`
- `data-skill-name` from `name`
- `data-skill-type` from `type`
- `data-skill-description` from `description`

Its text is the skill name. JSON also retains `key`. A vacant skill slot is an
attribute-free direct `li` with no JSON object at that position. The Phase 0
round trip preserved a recognized default skill, a synthetic original skill,
and four trailing vacant slots.

### Personality keywords

`ul#personality-value` contains six direct `li` slots. A selected catalog
keyword is represented by its name as element text and by the same-position
object in `data.personalities`, containing `id`, `name`, `type`, and `karma`.
Unselected slots are attribute-free.

### Memories

`ul#memories-value` always contains six direct `li` slots. A displayed normal
memory uses:

- `data-memory-id` from `id`
- `data-memory-title` from `title`
- `data-memory-summary` from `summary`
- `data-memory-location` from `location`
- `data-memory-intent` from `intent`
- `data-memory-outcome` from `outcome`
- `data-memory-tags` from the ordered JSON `tags` array

Its text is the title. A placeholder memory or an absent array position is an
attribute-free direct `li`.

Array positions zero through five determine the six HTML slots. Positions six
and later exist only in `data.memories`. The Phase 0 round trip retained eight
objects and the alternating normal/placeholder sequence while re-emitting only
six HTML slots. Moving an object across this boundary therefore changes only
which six HTML fragments are displayed; it must not reserialize an otherwise
unedited JSON object.

## Safe embedding and offline behavior

Application-authored HTML contains no JavaScript, event attributes, external
scripts, external stylesheets, external images, web fonts, or network links.
Its CSP is:

```text
default-src 'none'; img-src data:; style-src 'unsafe-inline'
```

Element text and attributes use context-specific HTML escaping. Embedded JSON
escapes `<`, `>`, and `&`, so user text containing `</script>` cannot terminate
the data script. The document must cause no external communication.

## Save diagnostics and same-byte guarantee

Each load records a `DiagnosticBaseline` for name, profile, status, icon,
skills, personalities, and memories. A section baseline contains its editability,
diagnostic codes and severity, JSON/HTML counts, position-correspondence state,
read-only reason, and the section's JSON and HTML bytes.

For a known format, an existing section mismatch does not make unrelated
sections uneditable. A save is valid when:

- each load-time read-only section retains identical JSON and HTML bytes;
- its diagnostic facts remain identical to the load-time baseline;
- every load-time editable section remains editable after rendering;
- no new mismatch is introduced; and
- `formatVersion` remains unchanged and known.

Returning a sparse draft to all baseline values returns the original `bytes`
object. An unchanged Save As writes those bytes without serializing the JSON or
HTML. A successful atomic save reads the destination again and establishes it
as the new path and baseline. An error before or after the temporary write
does not change the current baseline, path, draft, or unsaved-change state.

Qt population is not edit intent. Initial `setText`/`setPlainText` operations
block signals, and untouched text is rendered from original JSON tokens and
HTML fragments. This preserves LF, CRLF, lone CR, and existing JSON escape
spellings even where a Qt multiline control displays a normalized newline.

## Consequences

- `formatVersion == "1.0.0"` is the only editable format established by the
  private-corpus survey and Phase 0.
- Unknown versions remain whole-sheet read-only.
- The game-export HTML wrapper and the application-authored browser view may
  differ without implying a JSON incompatibility.
- Game normalization is considered only by the Phase 0 comparison tool. It
  does not relax byte preservation for ordinary editor saves.
- The v2 implementation uses the byte-preserving character-sheet model and
  save validation described above.
