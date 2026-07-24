# Repository Instructions

This repository contains the Windows desktop application "Saga & Seeker Skill Editor".
Keep user-owned character sheet HTML safe even when an input format is unfamiliar.

## Start Here

Before changing code, read these files in order:

1. `CONTEXT.md` for the canonical domain language.
2. `docs/HANDOFF.md` for the current product and implementation state.
3. Relevant decisions under `docs/adr/`.
4. `README.md` for user-facing behavior and commands.

Treat the implementation and tests as the final authority when documentation disagrees.
Surface the disagreement before changing behavior.

## Non-Negotiable Safety Rules

- Never edit a user's source character sheet in place. The GUI saves to a separately selected destination.
- Treat input HTML as bytes. Do not normalize the full document, its JSON, whitespace, or newlines.
- Patch only the intended JSON tokens or one intended object and the corresponding direct-child HTML `li`.
- Preserve unedited skill and personality objects, unknown fields, unknown attributes, and unaffected HTML byte-for-byte.
- Escape JSON written inside `script#character-sheet-data` so `<`, `>`, and `&` cannot terminate or alter the script element.
- Escape HTML attribute values and text content for their separate contexts.
- Match JSON arrays to HTML by array position and direct-child display order, not by ID.
- Count only `ul#skills-value > li` and `ul#personality-value > li`. Do not count descendant `li` elements.
- If structure or position correspondence cannot be established safely, use read-only behavior instead of guessing.
- Preserve arbitrary valid skill IDs. Do not convert an existing AI-generated or non-`skN` ID.
- Do not repair pre-existing empty or duplicate IDs unless that skill is edited and the user explicitly consents.
- Generate an unused positive `skN` only for new, repaired, or default-replacement original skills.
- Keep protected default-skill replacement in the advanced flow with two confirmations.
- Save through a same-directory temporary file, `flush`, `fsync`, reload validation, and `os.replace`.
- A save failure must leave the current in-memory edits available for retry.
- Personality keywords are catalog-only. Do not add free-form personality keyword creation.
- Never commit real character sheets, embedded Base64 images, personal settings, private fixtures, generated EXEs, or build directories.

## Architecture

- `src/saga_seeker_skill_editor/core/`: byte parsing, classification, patch rendering, and atomic file writing. It must not depend on Qt.
- `src/saga_seeker_skill_editor/gui/`: PySide6 widgets, state presentation, dialogs, themes, and settings.
- `src/saga_seeker_skill_editor/data/`: packaged personality keyword catalog.
- `src/saga_seeker_skill_editor/resources.py`: the single resource-resolution boundary for source, onedir, and onefile execution.
- `tests/`: synthetic public tests and the ignored private-fixture integration harness.

Do not move HTML editing semantics into GUI widgets. GUI code should collect intent and delegate rendering to `core`.

## Development Workflow

Install the project environment:

```powershell
uv sync --extra dev --extra build
```

Run the application:

```powershell
uv run python -m saga_seeker_skill_editor
```

Run public tests using a repository-local temporary directory:

```powershell
uv run pytest -q --basetemp=work\pytest-agent -o cache_dir=work\.pytest-agent-cache
```

Run private integration tests only against copies or read-only originals:

```powershell
$env:SAGA_SEEKER_PRIVATE_FIXTURES = "C:\path\outside\the\repository"
uv run pytest -q --basetemp=work\pytest-private -o cache_dir=work\.pytest-private-cache
```

Build Windows distributions:

```powershell
powershell -ExecutionPolicy Bypass -File .\build.ps1 -Mode onedir
powershell -ExecutionPolicy Bypass -File .\build.ps1 -Mode onefile
```

`build.ps1` runs the test suite before invoking PyInstaller. Verify both executables and all three themes before a release.

## Test Expectations

- Add or update focused tests for every behavior change.
- Include round-trip tests for special characters whenever JSON or HTML output changes.
- Verify unchanged byte segments for any new patch operation.
- Cover safe read-only fallback for unsupported structures.
- GUI tests must isolate `QSettings` from the real user profile and use offscreen Qt where appropriate.
- Do not weaken a safety assertion merely to accept a new real-world sheet; first establish the format and encode its rule explicitly.

## Git and Release Safety

Before staging or committing, inspect:

```powershell
git status --ignored
git diff --cached --name-only
git check-ignore .venv dist work tests/private_fixtures
```

Stop if real HTML, private fixtures, generated EXEs, `dist`, `build`, `work`, or `.venv` are staged.
Do not invent Git identity settings. Releases use semantic version tags and include onefile, onedir ZIP, and `SHA256SUMS.txt`.

## Documentation Maintenance

- Update `CONTEXT.md` only when canonical domain terminology changes.
- Add or supersede an ADR when reversing a recorded architectural decision.
- Update `docs/HANDOFF.md` when release state, supported workflows, known risks, or verification commands materially change.
- Keep public documentation free of personal absolute paths and game-derived character sheet contents.

## Agent skills

### Issue tracker

Issues and PRDs are tracked in this repository's GitHub Issues. See `docs/agents/issue-tracker.md`.

### Triage labels

Use the five standard triage roles and label strings. See `docs/agents/triage-labels.md`.

### Domain docs

This is a single-context repository with one root glossary and root ADR directory. See `docs/agents/domain.md`.
