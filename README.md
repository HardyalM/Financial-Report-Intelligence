# Financial Report Intelligence & RAG

**Status: under construction (v1 in progress).** Nothing here is ready to use yet.

Upload a UK annual report PDF → extract the primary statements into a typed `StatementPack` →
calculate locked ratios in Python → grounded commentary with verified page citations → one-screen
analyst dashboard. Numbers never come from a language model.

- Plan and scope: [`docs/PLAN.md`](docs/PLAN.md)
- Architecture: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- Progress and gates: [`docs/MILESTONES.md`](docs/MILESTONES.md)
- Rules every contributor (human or AI) follows: [`CLAUDE.md`](CLAUDE.md)

## Development

Requires [uv](https://docs.astral.sh/uv/) and Python 3.12.

```bash
uv sync          # creates the virtual environment with dev tools
make ci          # lint, typecheck, tests, contract drift and scope checks
```

Research aid only. Not investment advice.
