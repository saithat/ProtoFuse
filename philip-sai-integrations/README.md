# Philip–Sai integration scenarios (`philip-sai-integrations/`)

This directory is separate from `src/protofuse/integration/`, which holds shared
**code** for compiling `MethodologySpec` into `ProtoPlan`. Here we keep **versioned
paper and workflow scenarios** with explicit, mixed Philip–Sai attribution.

Sai can pick his own paper and workflow quickly under `v1/sai/`. The repo owner can
add workflows under `v1/contributed/`. Joint scenarios live under `v1/mixed/`.

```text
philip-sai-integrations/
└── v1/
    ├── catalog.json              # versioned index; commit when adding scenarios
    ├── sai/                      # Sai-selected papers/workflows
    ├── contributed/              # owner-provided workflows
    └── mixed/                    # joint Sai + owner (or Phillip) scenarios
```

Each scenario is a directory:

```text
v1/<lane>/<scenario_id>/
├── manifest.json                 # contributors, lane, version, status
└── methodology.json              # redistributable MethodologySpec (no raw paper text)
```

Optional graph handoff artifacts link through `handoff_decision_id` into
`philip-sai-workflow-dump/phillip_to_sai/<decision_id>/` and
`philip-sai-workflow-dump/sai_to_phillip/<decision_id>/`.

## Versioning

- **Integration version** (`v1`, `v2`, …): bump when manifest or catalog schema changes.
- **Scenario version** (`scenario_version` in `manifest.json`): bump when the workflow
  or methodology for that scenario changes materially.
- Register every scenario in `v1/catalog.json` so attribution and status stay auditable.

## Quick start for Sai

```bash
cp -R philip-sai-integrations/v1/sai/_template philip-sai-integrations/v1/sai/<scenario_id>
# edit manifest.json and methodology.json
# add an entry to philip-sai-integrations/v1/catalog.json
uv run protofuse integrations validate
```

## Quick start for contributed workflows

```bash
mkdir -p philip-sai-integrations/v1/contributed/<scenario_id>
# add manifest.json and methodology.json
# add an entry to philip-sai-integrations/v1/catalog.json
uv run protofuse integrations validate
```

Only commit redistributable methodology JSON. Raw paper text, sequences, credentials,
and large run artifacts stay under ignored `data/`.
