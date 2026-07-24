# Issue Tracker: GitHub

Issues and PRDs for this repository live in GitHub Issues:

`https://github.com/shirogitsune-lab/saga-seeker-skill-editor/issues`

Use the connected GitHub app when available. The `gh` CLI may be used from an authenticated local checkout.

## Conventions

- Create one issue per user-visible defect, feature, or documentation task.
- Record reproduction steps, expected behavior, actual behavior, affected sheet shape, and safety impact for defects.
- Do not attach real character sheets publicly. Replace private content with a minimal synthetic reproduction.
- Link accepted implementation decisions to the relevant ADR.
- Close an issue only after focused tests and the appropriate regression suite pass.

Common CLI operations:

```powershell
gh issue create --title "..." --body "..."
gh issue view <number> --comments
gh issue list --state open
gh issue comment <number> --body "..."
gh issue edit <number> --add-label "..."
gh issue close <number> --comment "..."
```

Infer the repository from `git remote -v` when running inside this checkout.

## Pull Requests as a Triage Surface

PRs as a request surface: no.

External pull requests may still be reviewed, but they are not treated as the canonical feature-request queue unless this policy is changed here.

## Skill Integration

- When a skill says "publish to the issue tracker", create a GitHub issue.
- When a skill says "fetch the relevant ticket", read the corresponding GitHub issue and its comments.
- A bare `#42` may refer to either an issue or pull request because GitHub shares the number space; resolve the type before acting.
