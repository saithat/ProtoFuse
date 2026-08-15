# ProtoFuse

ProtoFuse turns a scientific paper into an auditable methodology specification,
matches it to a reusable workflow topology, and produces a Proto-oriented execution
plan.

```text
paper -> scientific agent -> methodology spec -> topology selection
      -> folder of Proto programs -> selective learned fusion -> executable workflow
```

The important integration boundaries are the versioned `MethodologySpec` and Phillip's
reviewed folder of generated Proto programs. Phillip owns the paper-to-Proto path. Sai
profiles recurring model-step groups across those programs and prototypes a multi-output
surrogate that defers uncertain or out-of-domain inputs to the original full models.

## Team split

| Area | Primary | Shared with |
| --- | --- | --- |
| `src/protofuse/scientific_agent/` | Phillip + Sai | both |
| `src/protofuse/phillip/` | Phillip | paper-to-Proto collection generation |
| `src/protofuse/sai/` | Sai | catalog, profiling, learned fusion, and evaluation |
| `src/protofuse/contracts.py` | Phillip + Sai | both; change deliberately |
| `src/protofuse/integration/` | Phillip + Sai | both |
| `proto_programs/` | Phillip | Sai consumes frozen collections |
| `workspaces/phillip/` | Phillip | isolated experiments |
| `workspaces/sai/` | Sai | isolated experiments |

See [docs/TEAM.md](docs/TEAM.md) for the direct-to-main collaboration rules and
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the interface between the two tracks.

## Start here

```bash
uv sync --extra dev
cp .env.example .env
uv run pytest
uv run protofuse validate examples/toy_methodology.json
uv run protofuse recommend examples/toy_methodology.json
uv run python examples/proto_smoke.py
```

After configuring an Anthropic key, extract a paper text file with:

```bash
uv run protofuse extract path/to/paper.txt --out data/specs/paper.json
```

Account authentication is intentionally separate from package installation. Complete
the short checklist in [docs/SETUP.md](docs/SETUP.md) for Anthropic, Paperclip, Modal,
and any gated Hugging Face models.

## What is executable today

The local toy methodology validates and receives a topology recommendation. The
compiler emits a `ProtoPlan` and lists any paper-specific component names that still
need binding to concrete Proto classes/functions. That explicit unresolved list is the
safety gate between text extraction and code execution.
