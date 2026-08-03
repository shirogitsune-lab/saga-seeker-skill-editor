# Separate public synthetic and private real-sheet fixtures

Real character sheets may contain embedded images, personal settings, and game-derived content that should not be published. The repository therefore contains only minimal synthetic HTML fixtures, while real sheets remain ignored private fixtures or external read-only inputs used for local integration tests.

## Consequences

- `tests/private_fixtures/` is ignored except for its placeholder.
- `SAGA_SEEKER_PRIVATE_FIXTURES` may point tests at an external private directory without recording that path.
- Private integration tests select scenarios from sheet structure, not from
  committed filenames, and retain neither filenames nor paths in their
  anonymous in-memory fixture records.
- The `private_integration` marker excludes those tests from public CI. Their
  local skip reasons are fixed generic messages rather than missing-file lists.
- Public CI verifies generated JUnit XML before upload and does not publish the
  report Artifact when the XML contains a character-sheet filename or an
  absolute local path.
- Tests that write must operate on temporary copies and never edit originals.
- A staged real HTML file, generated EXE, Base64 image, or private fixture blocks a commit.
