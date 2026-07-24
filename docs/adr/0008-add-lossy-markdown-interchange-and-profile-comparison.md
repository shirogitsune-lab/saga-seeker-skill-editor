# Add lossy Markdown interchange and shared profile comparison

## Context

Users need to compare profile prose, especially `basicSettings` and
`personality`, while consulting selected personality keywords. They also use a
separate Rust HTML-to-Markdown utility to prepare character information for AI
tools and asked for that workflow inside this editor.

The standalone converter intentionally discards images and internal
character-sheet identity. Its Markdown therefore cannot reproduce the original
HTML or JSON. It does, however, retain useful skill descriptions by combining
HTML attributes with embedded JSON, including valid skills whose `type` is
empty.

## Decision

The basic-information tab normally exposes all seven profile field names as
independently checkable accordion headers. `basicSettings` starts expanded and
the other fields start collapsed. Users may expand multiple fields at once.
All seven editor widgets stay alive, so collapsing and expanding preserves
their content and cursor positions. Accordion state is presentation state and
is not edit intent. A horizontal splitter lets the user allocate width between
profile editing and the image controls.

The comparison workspace remains hidden by default. An explicit show command
reveals two selectable profile editors plus a read-only, live
personality-keyword reference. The three panes use a horizontal splitter. The
two editors are synchronized views over the existing `CharacterSheetDraft`;
they do not own copied domain state. The comparison panel may be reparented
into one non-modal window. Closing the inline view or separate window reparents
the same widgets into the hidden tab host. Population, accordion toggling,
selection, resizing, show, hide, detach, and close are not edit intent.

Markdown export is implemented in-process through
`render_ai_markdown(CharacterSheet)`. The GUI first renders the current draft
in memory with the existing character, skill, and personality renderers, loads
that result, and projects semantic data to UTF-8 Markdown. It does not invoke
the standalone executable or its batch `input`/`output` folders.

The export contains:

- name and all seven profile fields;
- selected personality names and order;
- the six visible statuses, excluding compatibility-only `charm`;
- skill names, descriptions, and order;
- all normal memories, including positions seven onward, with their content and
  tags.

It omits the image, character and memory IDs, timestamps, skill IDs/type/key,
vacant skill slots, placeholder memories, and charm. Export is a separate
atomic file write and never establishes a new HTML baseline or clears dirty
state.

Markdown import is intentionally partial. `parse_character_markdown` reads only
owned fixed headings from UTF-8 input no larger than 8 MiB. It does not render
Markdown, interpret HTML, follow links, or execute script. Before any current
sheet transition it produces a `MarkdownImportPlan` and a preview containing
all warnings and errors.

Import remains available after an HTML or blank sheet has been opened. The
loaded summary area exposes distinct `Markdownから新規作成` and
`Markdownを書き出す` controls; they do not share an ambiguous generic Markdown
button.

A successful import creates a new Phase 0-compatible sheet:

- imported name and seven profile fields;
- imported E–S values for six visible statuses;
- exact catalog personality keywords in contiguous slots;
- at most six imported skills, each as a new original skill with sequential
  `skN`, empty `type`, and empty `key`;
- default icon, charm `E`, no memories, and newly generated character ID and
  timestamp.

Unknown or duplicated catalog keywords, sparse or duplicated personality
slots, invalid ranks, more than six skills, and duplicated recognized sections
or profile fields are blocking errors. They are not silently normalized.
Legacy `（未入力）` is treated as empty with a warning. Legacy unnumbered
personality bullets are packed from slot one and disclosed in the preview.

## Compatibility evidence

The existing standalone converter's 151 local Markdown outputs were scanned
read-only without retaining names or content. The parser accepted 149 as
new-sheet candidates. It intentionally blocked one file with seven skills and
one file with a duplicated recognized profile heading. This is consistent with
the conservative import contract rather than a conversion failure.

## Consequences

- AI Markdown is clearly labeled as lossy and must not be described as a
  backup, archive, or exact round trip.
- Markdown import never claims to recover default-skill protection or internal
  identity.
- Images and memories must be set or edited in the character-sheet editor after
  import; memories are export-only.
- A parsing, validation, preview, or generation failure leaves the current
  sheet, path, baseline, and draft unchanged.
- The existing byte-preserving HTML save contract is unchanged.
