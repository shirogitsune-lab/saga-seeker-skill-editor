# Development Handoff

This document is the entry point for continuing development in a new Codex task.
Read `AGENTS.md` and `CONTEXT.md` first, then inspect the ADRs linked below.

## Baseline

- Product: Saga & Seeker Skill Editor
- Application version: `2.0.0` (implemented locally; not committed or released)
- Public release: `v1.2.0`
- Release tag commit: `8dd3fb4c0ab300b58d8558871a0d39b6eadc4328`
- Repository: `https://github.com/shirogitsune-lab/saga-seeker-skill-editor`
- Default branch: `main`
- License: MIT for the source code, bundled canary artwork, and distributions
- Platform: Windows 10/11 desktop
- Runtime: Python 3.11+ and PySide6; packaged users do not need Python

The local worktree now contains the accepted `v2.0.0` implementation on top of
the public `v1.2.0` baseline. No commit, push, tag, GitHub issue, or release has
been created.

## Product Purpose

The application lets Japanese-speaking players create and edit Saga & Seeker
character sheet HTML without manually editing embedded JSON. The ordinary
workflow is:

1. Open an existing HTML character sheet, create a blank one, or create a new
   sheet from supported Markdown fields.
2. Use the basic-information, status, skill, personality-keyword, or memory tab.
3. Edit or arrange supported content and optionally replace the icon.
4. Save under a different file name.

The current draft can also be exported as lossy AI-oriented Markdown without
changing the HTML baseline or unsaved-change state.

The original input file is not an in-place editing target. Safety and preservation of unknown source bytes take priority over accepting every possible sheet format.

## Current User Features

### Skills

- Shows every visible skill slot in a read-only, single-selection master list.
- Edits the name and description of recognized original skills.
- Supports original skills with arbitrary IDs, including game-AI-generated IDs.
- Adds manual original skills to explicit empty skills or trailing vacant slots.
- Allows drafting multiple vacant-slot additions before one save.
- Blocks saving when manual additions leave a gap before a later populated slot.
- Deletes a middle registered skill by replacing it with an explicit empty skill.
- Deletes the tail registered skill by removing its data object and returning the HTML position to a vacant slot.
- Replaces a protected default skill with an original skill through an advanced, two-confirmation operation.
- Offers either blank content or retained name/description when replacing a default skill.
- Requests explicit consent before repairing the ID of an edited original skill.

### Personality Keywords

- Provides the bundled catalog of 150 supported game-defined keywords.
- Selects up to six unique keywords with no gap between selected slots.
- Filters independently by system（力・知恵・富・愛・法）and karma（美徳・中庸・悪徳）.
- Searches by partial keyword-name match across systems and combines search with both filters.
- Adds catalog entries by button, Enter, or drag and drop.
- Reorders assigned keywords by drag and drop or up/down controls.
- Compacts later entries automatically when a middle keyword is deleted in the GUI.
- Rejects duplicates, out-of-catalog records, and non-contiguous saved selections.
- Does not support user-created personality keywords.

### Desktop Experience

- Uses a PySide6/Qt Widgets master-detail layout.
- Exposes four main states: unloaded, normal, modified, and error.
- Shows read-only and protected conditions as secondary badges.
- Recalculates modifications by comparing current values with the load/save baseline.
- Prompts Save As, Discard, or Cancel before leaving with unsaved changes.
- Preserves current edits after recoverable save errors.
- Provides light, dark, and high-contrast themes through `QSettings`.
- Defaults to light when no valid theme has been saved.
- Supports windowed or maximized startup display.
- Keeps technical fields and destructive actions behind progressive disclosure.
- Keeps profile comparison hidden by default and reveals it only through the
  explicit show command. The revealed workspace compares any two profile
  fields side by side while showing the live selected personality keywords.
- Moves the same comparison editors into a non-modal separate window and
  reparents them into the hidden basic-information host when that window
  closes. Show, hide, detach, and close are not edit intent.

### Markdown Interchange

- Exports the current rendered draft in-process; it does not launch or depend
  on the standalone Rust converter executable.
- Preserves the standalone converter's important semantic output, including
  descriptions for valid skills whose internal type is empty.
- Adds all normal memories, including JSON-only positions seven onward, to the
  AI-oriented export. Placeholder memories and internal IDs are omitted.
- Imports only fixed known headings from UTF-8 Markdown up to 8 MiB and never
  interprets embedded HTML.
- Creates a new sheet with the default icon, `charm == "E"`, no memories, and
  newly generated identity/timestamp metadata.
- Creates imported skills as new original skills with sequential `skN` IDs and
  empty `type`/`key`; protected default identity is never inferred.
- Requires exact catalog personality names and blocks unknown, duplicate,
  sparse, or over-limit input instead of silently repairing it.
- Shows a preview and warnings before replacement. Parse errors, validation
  errors, preview cancellation, and generation failure retain the current
  sheet and draft.

## Safety Contract

These rules are intentional architecture, not incidental implementation:

- The HTML file is parsed as bytes and never executed.
- Skill correspondence is `data.skills[index]` to the same-position direct child of `ul#skills-value`.
- Personality correspondence is `data.personalities[index]` to the same-position direct child of `ul#personality-value`.
- IDs are auxiliary validation and identity data, not position keys.
- Trailing plain vacant skill `li` elements may exist without JSON skill objects.
- The personality area must contain exactly six safe direct-child slots.
- Unknown or contradictory structure becomes read-only rather than being repaired speculatively.
- Existing valid IDs and unknown fields are retained.
- Existing empty or duplicate IDs remain untouched when their skills are not edited.
- JSON strings embedded in the script are script-safe.
- HTML attributes and element text use separate escaping rules.
- Only targeted JSON tokens or objects and corresponding HTML elements are replaced.
- The generated bytes are loaded again and checked before committing a save.
- Final writes are same-directory atomic replacements.

See:

- [ADR 0001: Preserve source bytes](adr/0001-preserve-source-bytes.md)
- [ADR 0002: Match by position](adr/0002-match-json-and-html-by-position.md)
- [ADR 0003: Classify conservatively](adr/0003-classify-skills-and-repair-ids-conservatively.md)
- [ADR 0004: Save atomically](adr/0004-validate-and-save-atomically.md)
- [ADR 0005: Catalog-only personalities](adr/0005-use-catalog-only-personality-keywords.md)
- [ADR 0006: Separate public and private fixtures](adr/0006-separate-public-and-private-fixtures.md)
- [ADR 0007: Define the v2 character-sheet contract](adr/0007-define-the-v2-character-sheet-contract.md)
- [ADR 0008: Add lossy Markdown interchange and shared profile comparison](adr/0008-add-lossy-markdown-interchange-and-profile-comparison.md)

## v2.0.0 Character-Sheet Editing

The accepted next version is `v2.0.0`. It adds new-sheet creation and
byte-preserving editing for the name, seven profile fields, six visible
statuses, icon, and memories while retaining the existing skill and personality
workflows.

### Phase 0 status

Phase 0 passed its manual game gate on 2026-07-24.

- The private anonymous survey examined 151 HTML files.
- One file had no character-sheet JSON script and none of the 150 discovered
  scripts failed JSON parsing.
- All 150 parsed documents had string `formatVersion` value `1.0.0`.
- `formatVersion`, `exportedAt`, and `data` were present in all parsed roots.
- `name`, `profile`, `status`, `skills`, `personalities`, `memories`, and
  `icon` were present in all parsed `data` objects.
- `characterId` was present in 37 of 150 parsed `data` objects, so its absence
  is an established existing form rather than an automatic corruption.
- Every known profile, status (including compatibility-only `charm`), and icon
  subkey was present in all 150 parsed sheets.

Both application-authored Phase 0 sheets imported and re-exported without a
user-visible game error. The all-section probe retained all structured values,
types, key order, skill and personality order, all eight memories, and
placeholder positions. The game regenerated identity/timestamp metadata,
rebuilt its presentation HTML, and re-encoded the same-size WebP. An empty name
was normalized from the export file name; a non-empty name was exact.

The candidates, re-exports, anonymous reports, and embedded icon remain private
and must not be committed. Public source contains only the deterministic
generator, privacy-safe analyzer/comparator, synthetic tests, and ADR 0007.
Phase 1 is now unblocked.

### v2.0.0 implementation state

The byte-preserving model, GUI, and save workflow are implemented:

- `load_character_sheet(raw)` records the parsed `formatVersion` and an
  immutable `DiagnosticBaseline` for name, profile, status, icon, skills,
  personalities, and memories.
- A present format version other than string `1.0.0` makes the whole sheet
  read-only. Version-less legacy synthetic inputs remain on the v1.2
  compatibility path; the private survey found no version-less real sheet.
- `CharacterSheetDraft` records only explicit edits relative to the loaded
  bytes. Displaying values creates no edit, and restoring the original name
  removes the edit.
- `render_character_sheet(sheet, draft)` returns the original bytes object when
  unchanged and supports targeted, script-safe name and profile JSON tokens plus
  their corresponding HTML text replacements.
- `create_character_sheet(...)` exposes the Phase 0 validated golden builder as
  the central new-sheet API.
- All seven profile tabs are matched by JSON key and `data-tab-key`.
- The six visible statuses are matched by order, `data-i18n-key`, rank, and six
  gauge segments. `charm` remains JSON-only. Status edits patch only the chosen
  JSON rank, displayed rank, and gauge segments.
- Memory loading validates the complete placeholder structure, normal-memory
  attributes, exact ordered tags, six HTML slots, and JSON-only positions seven
  onward.
- Normal-memory text and tag edits patch only selected JSON value tokens and
  corresponding HTML attributes/text. Unknown object keys, unknown HTML
  attributes, tag order, duplicates, whitespace, empty tags, and Unicode forms
  remain unchanged.
- Memory reorder moves original JSON object bytes, moves existing first-six HTML
  fragments as bytes, and generates HTML only when a JSON-only item crosses into
  the first six positions. Editing and reordering may be combined in one draft.
- Normal/placeholder conversion keeps the count stable. Normal conversion uses
  injected UUID/time/time-zone sources for the specified memory ID format.
- Removal decreases the array count; normal addition and placeholder fill stop
  at 15 total items. Existing over-limit sheets are retained and still permit
  count-neutral conversion and ordinary editing.
- Existing icon loading compares the JSON URI with `img#icon-value` without
  decoding the embedded image. Invalid image bytes therefore do not make other
  sections unreadable at load time.
- Icon replacement preflights encoded size, width, height, pixel count, and
  estimated peak buffers before decode. The crop dialog writes 512×512 WebP at
  quality 90 and keeps the prior draft on every failure.
- The start screen offers existing-sheet load and new-sheet creation. The
  editor has five tabs: basic information, status, skills, personality
  keywords, and memories.
- The basic-information tab exposes profile comparison on demand rather than
  showing it permanently. Normal editing shows all seven profile field names
  as independent accordion headers; `basicSettings` starts open, and users may
  expand multiple fields. Opening and closing fields preserves content and
  cursor position without creating draft intent. Once comparison is requested,
  it compares two selectable profile fields and shows live personality keywords.
  Splitter handles resize the normal profile/image panes and all three
  comparison panes. The comparison panel can move into a separate non-modal
  window without creating a second draft, and closing it returns to the hidden
  state.
- The start screen also offers Markdown partial import. Loaded sheets can
  import another Markdown file as a new sheet or export the current draft as
  AI-oriented Markdown without changing the HTML baseline or dirty state.
  Both operations have separate, explicitly labeled buttons in the loaded
  summary area as well as File-menu actions and keyboard shortcuts.
- GUI population blocks signals and does not write display-only newline
  conversion into the draft. Character counters use Python `len(str)` and
  preserve untouched source values.
- Unchanged Save As is enabled and writes the exact input bytes. Successful
  saves reload the destination as the new baseline; failed saves leave the
  baseline, path, and draft untouched.
- Save validation compares every load-time read-only section's JSON bytes,
  HTML bytes, diagnostic codes, severity, counts, correspondence, and reason.
  Editable sections must remain valid after rendering.
- The package metadata is `2.0.0`; the GUI title is
  `Saga & Seeker キャラクターシートエディター`. Executable, repository, and
  Python-package names remain unchanged.
- PyInstaller onedir and onefile definitions include the default WebP. The
  hidden `--image-smoke` path verifies PNG/JPEG decode, crop, WebP encode, and
  WebP reload inside the packaged executable.

## Code Map

| Area | Main files | Responsibility |
| --- | --- | --- |
| Application entry | `src/saga_seeker_skill_editor/main.py`, `gui/app.py` | QApplication setup and launch |
| Sheet loading | `core/character_sheet.py`, `core/html_locator.py`, `core/json_span.py` | Locate embedded data and direct HTML slots |
| Skill semantics | `core/skill_classifier.py` | Fixed-order skill classification and ID generation |
| Skill rendering | `core/sheet_editor.py`, `core/json_token_patcher.py`, `core/html_li_patcher.py` | Targeted byte-preserving edits |
| Personality catalog | `core/personality_catalog.py`, `data/personality_keywords.csv` | Load and validate all four catalog fields |
| Personality rendering | `core/personality_editor.py` | Targeted selection, order, append, and removal edits |
| Markdown interchange | `core/markdown_interchange.py` | Lossy semantic export, conservative fixed-heading import, new-sheet projection |
| Save boundary | `core/file_writer.py` | Same-directory atomic writing and temporary-file validation |
| Preservation helper | `core/invariant_segments.py` | Reusable unchanged-segment comparison helper; see the maintenance note below |
| Main GUI | `gui/main_window.py` | Load/save workflow, baselines, state, and dialogs |
| Character GUI | `gui/character_details_widget.py`, `gui/status_editor_widget.py`, `gui/memory_editor_widget.py` | v2 fields, counters, and memory intent |
| Image GUI | `gui/image_pipeline.py`, `gui/image_crop_dialog.py`, `gui/image_smoke.py` | bounded decode, crop, preview, packaged codec smoke |
| Skill GUI | `gui/skill_list_widget.py`, `gui/skill_editor_widget.py`, `gui/vacant_slot_editor_widget.py` | Skill selection and edit intent |
| Personality GUI | `gui/personality_editor_widget.py` | Filtering, validation, assignment, and drag/drop |
| Themes | `gui/theme_manager.py`, `gui/styles/*.qss` | Semantic tokens, QSS validation, persistence |
| Resources | `resources.py` | Source, onedir, and onefile resource resolution |
| Packaging | `SagaSeekerSkillEditor.spec`, `build.ps1` | PyInstaller builds and bundled resources |

`gui/theme.py` is a temporary compatibility re-export. Application code should import `theme_manager.py`; remove the compatibility module only in a separately verified cleanup.

## Validation

Install:

```powershell
uv sync --extra dev --extra build
```

Public suite:

```powershell
uv run pytest -q --basetemp=work\pytest-handoff -o cache_dir=work\.pytest-handoff-cache
```

The most recent local v2 verification recorded:

- Public run without private fixtures: `172 passed, 5 skipped`.
- Configured private real-sheet integration: `5 passed`; the anonymous corpus
  summary loaded all 150 valid character-sheet scripts and rejected the one
  HTML without a character-sheet JSON script.
- Read-only parsing of all 151 existing standalone-converter Markdown outputs
  accepted 149 as new-sheet candidates. Two were intentionally blocked: one
  exceeded the six-skill limit and one repeated a recognized profile heading.
- onefile and onedir builds completed.
- Both executable forms passed PNG/JPEG decode, square crop, WebP encode, WebP
  reload, and packaged default-WebP resolution.
- Both executable forms launched successfully with light, dark, and
  high-contrast themes.

Pytest's default Windows temp or cache directory may be inaccessible on some machines. Keep `--basetemp` and `cache_dir` under ignored `work/`, or use `build.ps1`, which already does this.

Private integration:

```powershell
$env:SAGA_SEEKER_PRIVATE_FIXTURES = "C:\path\outside\the\repository"
uv run pytest -q --basetemp=work\pytest-private -o cache_dir=work\.pytest-private-cache
```

Never modify a private fixture original. Tests must read originals or copy them to a temporary destination first.

## Build and Release

```powershell
powershell -ExecutionPolicy Bypass -File .\build.ps1 -Mode onedir
powershell -ExecutionPolicy Bypass -File .\build.ps1 -Mode onefile
```

- onedir output: `dist/SagaSeekerSkillEditor/`
- onefile output: `dist/SagaSeekerSkillEditor.exe`
- `Pillow` is used only to convert the icon before packaging and is excluded from the onefile bundle.
- QSS, the icon, and the personality catalog must work in source, onedir, and onefile execution.
- Release assets should include a versioned onefile EXE, a versioned onedir ZIP, and `SHA256SUMS.txt`.
- The binaries are unsigned, so Windows SmartScreen may warn.
- onefile is convenient as one executable; onedir is equally supported and may start faster or attract fewer antivirus false positives.

## Public Repository Boundaries

Allowed:

- Source code
- MIT-licensed project artwork
- The compatibility personality mapping needed by the editor
- Minimal synthetic HTML fixtures

Not allowed:

- Real character sheet HTML
- Embedded Base64 character images
- Personal settings or absolute personal paths
- Private fixtures
- Generated EXEs and build output

The game-derived names and classification data in `data/personality_keywords.csv` are explicitly excluded from the repository's MIT grant as described in `README.md`.

## Current Maintenance State

- The accepted v2.0.0 feature, profile comparison, and Markdown interchange are
  implemented locally. The latest public and private suites pass. Both onedir
  and onefile were rebuilt after the Markdown/UI additions and passed the
  packaged image pipeline plus light, dark, and high-contrast GUI smoke.
- Use GitHub Issues for the next feature request or defect before substantial implementation.
- `core/invariant_segments.py` exists, but the production save path does not currently call it. Byte preservation is provided by targeted replacements and focused tests. Before claiming universal runtime invariant-segment validation, either integrate the helper into the render/save path with tests or narrow the README statement.
- The release announcement presented v1.2.0 as the first advertised update after v1.0.0; v1.1.0 existed publicly but was not separately advertised.
- The README currently describes onefile as the usual download. Both onefile and onedir are valid; future wording may present them as convenience versus startup/operational trade-offs.
- Phase 0 through Phase 6 implementation is present. Do not import private
  round-trip files, reports, or embedded images into the repository.

## New Task Startup Checklist

In a fresh Codex task:

1. Read `AGENTS.md`, `CONTEXT.md`, this file, and relevant ADRs.
2. Run `git status --short --branch` and confirm the intended baseline.
3. Inspect the issue or user request and identify affected core and GUI boundaries.
4. Run the focused baseline tests before editing.
5. Preserve unrelated user changes in a dirty worktree.
6. Implement with focused tests, then run the full public suite.
7. For a release, verify ignored/staged files, both PyInstaller forms, and all three themes.

Suggested opening instruction:

> Continue development of `saga-seeker-skill-editor`. First read `AGENTS.md`, `CONTEXT.md`, `docs/HANDOFF.md`, and relevant files under `docs/adr/`. Confirm Git status and baseline tests before changing code. Do not relax the byte-preservation, read-only fallback, ID-preservation, private-fixture, or atomic-save rules without explicit approval.
