# Projects

All new work in this repository must be created under `projects/`.

## Naming

- Use `projects/<project-slug>/`
- `project-slug` must be lowercase kebab-case

Examples:

- `projects/chat-ui/`
- `projects/data-pipeline/`
- `projects/agent-tools/`

## Minimum Project Template

Each project should start with:

```text
projects/<project-slug>/
├── README.md
├── src/      # optional
├── tests/    # optional
└── docs/     # optional
```

Each project `README.md` should describe:

- Goal
- Tech stack
- How to run it
- Current status

Shared tooling or package workspace setup is intentionally deferred until there is a real need for cross-project reuse.
