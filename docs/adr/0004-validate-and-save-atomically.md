# Validate and save atomically

Saving must not leave a partially written or structurally invalid character sheet. The application confirms overwrite before creating a temporary file, renders and validates in memory, writes a temporary file in the destination directory, flushes and `fsync`s it, reloads it for validation, and only then commits it with `os.replace`.

## Consequences

- A failed save removes only the temporary file and retains the user's in-memory edits.
- Recoverable destination errors do not force the loaded sheet into read-only mode.
- Validation code must be usable against both in-memory bytes and the temporary path.
- Direct writes to the destination or cross-directory temporary files are not acceptable substitutes.
