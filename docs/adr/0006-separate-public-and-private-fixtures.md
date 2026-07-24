# Separate public synthetic and private real-sheet fixtures

Real character sheets may contain embedded images, personal settings, and game-derived content that should not be published. The repository therefore contains only minimal synthetic HTML fixtures, while real sheets remain ignored private fixtures or external read-only inputs used for local integration tests.

## Consequences

- `tests/private_fixtures/` is ignored except for its placeholder.
- `SAGA_SEEKER_PRIVATE_FIXTURES` may point tests at an external private directory without recording that path.
- Tests that write must operate on temporary copies and never edit originals.
- A staged real HTML file, generated EXE, Base64 image, or private fixture blocks a commit.
