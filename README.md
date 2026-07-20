# Saga & Seeker Skill Editor

Saga & Seeker Skill Editor is a local Windows GUI application for safely editing only the skill fields in Saga & Seeker character sheet HTML files.

## User Interface

The PySide6 application uses a master-detail layout. The left pane is a read-only, single-selection skill overview; the right pane edits the selected skill. Technical metadata and destructive default-skill replacement are kept in separate disclosure sections.

All visual skill slots are shown in the list. Any vacant slot can be edited before saving, and several consecutive skills can be added in one operation. If an earlier slot is left blank, the editor marks the gap and blocks saving until the skills are contiguous from the front. Skill deletion is kept under Advanced Operations as one contextual action. Deleting a middle item replaces it with an explicit empty skill to preserve positional mapping, while deleting the last registered item returns that slot to a vacant state where the game may add a skill automatically.

Main shortcuts:

- `Ctrl+O`: open a character sheet HTML file
- `Ctrl+Shift+S`: save edited content under a new name
- `F5`: reload the current file
- `F6`: move focus between the skill list and editor
- `Ctrl+W`: close the application

Unsaved changes are always resolved through Save As, Discard, or Cancel before a file switch, reload, or exit.

The `View > Appearance` menu provides Light, Dark, and High Contrast themes. Light is used on first launch. The selected theme is restored with `QSettings` on later launches, while temporary theme-resource failures fall back without overwriting the user's saved choice.

## Windows Builds

Prebuilt Windows x64 packages are published on the GitHub Releases page in two forms:

- `onefile`: one standalone executable
- `onedir`: a ZIP containing the executable and its runtime files

The executables are not code-signed, so Windows SmartScreen may display a warning. Verify downloaded files against the release's `SHA256SUMS.txt` before running them. The application edits local files only and does not perform network communication.

## Core Safety Rules

- The app must not execute JavaScript from input HTML.
- The app must not use network communication.
- `data.skills` and `ul#skills-value > li` are matched by position, not by ID.
- Direct child `li` elements of `ul#skills-value` are the only HTML skill elements.
- The HTML always has visual skill slots. Plain trailing `<li>&nbsp;</li>` elements with no attributes are vacant slots and do not require matching `data.skills` objects.
- An explicit empty-skill object is still a real `data.skills` entry used to occupy a slot and prevent automatic skill generation. It is not treated as a vacant slot.
- Extra HTML entries containing attributes, child elements, or visible text remain a structure mismatch and force read-only mode.
- New manual skills are appended one object at a time and occupy consecutive vacant slots from the front. Multiple consecutive additions can be saved together; gaps block saving.
- Deleting a middle skill replaces only its JSON object and `li` with an explicit empty skill. Deleting the tail skill removes only that final JSON object and restores its `li` as a vacant slot.
- Skill IDs have no format restriction. Only non-string IDs, empty string IDs, and exact duplicate IDs require repair when the affected skill is edited.
- Existing empty or duplicate IDs are not repaired on load.
- Saving must use a same-directory temporary file, flush and fsync, reread validation, then `os.replace`.

## Dependencies

Runtime dependency:

- PySide6

Development and build dependencies:

- pytest
- PyInstaller
- Pillow

Pillow is for icon conversion during build preparation. It should not be required by the distributed application at runtime unless a later phase deliberately adds runtime image conversion.

## Build Notes

The source WebP icon is kept at `assets/カナリア.webp`. Run `scripts/convert_icon.py` to generate `assets/kanaria.ico` before packaging.

`SagaSeekerSkillEditor.spec` sets the EXE icon and packages `gui/styles/*.qss` for PyInstaller onefile builds. The build script includes the same theme resources in onedir builds. Runtime resource lookup supports PyInstaller's `_MEIPASS` extraction directory from one centralized helper.

## Fixtures

Public tests must use minimal synthetic fixtures only.

Real character sheet HTML files, Base64 images, personal settings, and game-derived content must stay out of Git. Put local integration fixtures under:

```text
tests/private_fixtures/
```

That directory is ignored except for `.gitkeep`.

Alternatively, set `SAGA_SEEKER_PRIVATE_FIXTURES` to a private directory containing local character sheet HTML files before running the integration tests. The path itself is not stored in the repository.

## License And Assets

This project is released under the [MIT License](LICENSE). The license covers the source code and bundled canary application icon. Built executables are distributed under the same terms.

Saga & Seeker, its game content, and related names belong to their respective rights holders. This project is an unofficial interoperability tool and is not affiliated with or endorsed by the game developer or publisher. Character sheet HTML files and other game-derived content are not distributed with this repository.

Public tests contain only minimal synthetic fixtures created for this project. Local private fixtures remain excluded from Git.
