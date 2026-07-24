# Domain Docs

This is a single-context repository.

## Before Exploring

Read:

- `CONTEXT.md` at the repository root for canonical product language.
- Relevant decisions under `docs/adr/` before changing the associated behavior.
- `docs/HANDOFF.md` for the current implementation and release state.

If one of these files is absent, continue without inventing its contents.

## Structure

```text
/
├── CONTEXT.md
├── docs/
│   ├── HANDOFF.md
│   ├── agents/
│   └── adr/
└── src/
```

## Vocabulary

Use the terms defined in `CONTEXT.md` in issue titles, specifications, tests, UI proposals, and documentation. In particular, do not conflate an explicit empty skill（空スキル）with a vacant skill slot（未使用枠）.

If a new feature introduces a genuinely new domain concept, update the glossary through the domain-modeling process. Keep implementation details in code, ADRs, or `HANDOFF.md`, not in the glossary.

## ADR Conflicts

If proposed work contradicts an existing ADR, identify the conflict explicitly. Either preserve the decision or create a superseding ADR with the user's approval; do not silently override it.
