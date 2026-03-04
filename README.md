# AI_coding

`AI_coding` is the central monorepo for future development work. All new projects live under `projects/` and follow a consistent structure so they can be managed in one place.

## Repository Rules

- Put every standalone project in `projects/<project-slug>/`.
- Use lowercase kebab-case for project directory names.
- Keep project code out of the repository root.
- Add a `README.md` to every project with its goal, stack, setup, and current status.

## Adding a New Project

1. Create `projects/<project-slug>/`.
2. Add a `README.md` that explains purpose, tech stack, run steps, and status.
3. Add `src/`, `tests/`, or `docs/` only when the project needs them.
4. Commit the new project together with any required repository-level documentation updates.

## Git Workflow

- Default branch: `main`
- Default remote: `origin`
- Remote URL: `git@github.com:bigboywwn/AI_coding.git`

For solo work, direct commits to `main` are acceptable. If multiple efforts run in parallel later, short-lived feature branches can be introduced.

## Docs

- `docs/mooncake-analysis.md`: persisted analysis of the `Mooncake` repository architecture, `Transfer Engine`, and `MasterService`
