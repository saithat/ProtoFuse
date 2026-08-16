# /// script
# [tool.marimo.display]
# theme = "dark"
# default_width = "full"
# cell_output = "above"
# ///

"""ProtoFuse hackathon progress dashboard for GXL demo."""

import marimo

__generated_with = "0.23.16"
app = marimo.App(width="full")


@app.cell(hide_code=True)
def _():
    import json
    from pathlib import Path
    from textwrap import dedent

    import marimo as mo
    import pandas as pd

    mermaid_init = '%%{init: {"flowchart": {"wrappingWidth": 420}} }%%'

    return Path, dedent, json, mermaid_init, mo, pd


@app.cell(hide_code=True)
def _(Path, json, pd):
    REPO = Path(__file__).resolve().parents[1]

    COLLECTION_META: dict[str, dict[str, str]] = {
        "dnachisel-num1": {
            "domain": "DNA",
            "primary_program": "design_001.py",
            "tool_chain": "DNAChisel constraints",
            "sai_note": "CPU codon work — weak fusion target",
            "summary": (
                "Codon-optimize the NUM1 CDS from DNA Chisel (Zulkower & Rosser 2020) "
                "with region-local MCMC. `design_001.py` is one inner step of the 936 bp "
                "gene-scale loop; `design_002.py` is the reduced smoke tier."
            ),
        },
        "custom-egfp-lung": {
            "domain": "DNA / mRNA",
            "primary_program": "design_001.py",
            "tool_chain": "Pool optimizer",
            "sai_note": "CPU pilot — OLS surrogate on codon score + GC",
            "summary": (
                "Tissue-specific eGFP codon pool from CUSTOM (Hernandez-Alias et al. 2023). "
                "Sai's regression pilot: 1,198 train / 396 cal / 398 audit samples grouped "
                "by trajectory chain."
            ),
        },
        "esm2-protein-maturation": {
            "domain": "Protein",
            "primary_program": "design_001.py",
            "tool_chain": "ESM-2 + ESMFold MCMC",
            "sai_note": "Modal smoke full-model summary captured",
            "summary": (
                "Developability / stability maturation of lysozyme (129 aa). ESM-2 proposes "
                "mutations; ESMFold scores every accept/reject."
            ),
        },
        "antibody-cdr-maturation": {
            "domain": "Antibody",
            "primary_program": "design_001.py",
            "tool_chain": "AbLang CDR MCMC",
            "sai_note": "Strong fusion target; smoke final in viz bundle",
            "summary": (
                "Region-local CDR maturation on a 121-aa nanobody. ESM-2 mutates the active "
                "CDR only; AbLang, ESMFold ipTM, complexity, and gap Gini score each proposal."
            ),
        },
        "gpcr-cxcr4-miniprotein": {
            "domain": "GPCR binder",
            "primary_program": "design_001.py",
            "tool_chain": "RFdiffusion3 + Boltz-2",
            "sai_note": "Modal smoke full-model summary captured",
            "summary": (
                "De novo miniprotein binder to CXCR4. RFdiffusion3 designs the backbone, "
                "ProteinMPNN assigns sequence, and Boltz-2 scores against 4RWS hotspots."
            ),
        },
        "boltz2-state-sweep": {
            "domain": "Conformational states",
            "primary_program": "design_001.py",
            "tool_chain": "Boltz-2 state sweep vs 4GBY/4GBZ",
            "sai_note": "Recommended target — labelled RMSD ground truth",
            "summary": (
                "Fixed XylE sequence; sweep Boltz-2 controls to surface the alternative "
                "conformational state, then score by RMSD against 4GBY/4GBZ."
            ),
        },
        "freebindcraft-binder": {
            "domain": "Protein binder",
            "primary_program": "design_001.py",
            "tool_chain": "FreeBindCraft rejection sampling",
            "sai_note": "Structure validation per candidate",
            "summary": (
                "BindCraft-style de novo mini-protein binder with rejection sampling on "
                "interface and structure metrics (ipTM, pLDDT, RMSD)."
            ),
        },
        "symmetric-oligomer-ring": {
            "domain": "Oligomer",
            "primary_program": "design_001.py",
            "tool_chain": "C6 symmetric pool",
            "sai_note": "Protein scorer is still a DNA-heuristic proxy",
            "summary": (
                "Design sequences that assemble into a C6-symmetric ring via pool optimizer."
            ),
        },
        "ppi-interface-specificity": {
            "domain": "PPI specificity",
            "primary_program": "design_001.py",
            "tool_chain": "Dual target / off-target scoring",
            "sai_note": "AF3 specificity is a protein–DNA proxy in frozen programs",
            "summary": (
                "Region-local MCMC on interface patches for on-target binding vs off-target."
            ),
        },
        "rfdiffusion3-boltz2-binder": {
            "domain": "Protein binder",
            "primary_program": "design_001.py",
            "tool_chain": "RFdiffusion3 bootstrap + Boltz-2 cycling",
            "sai_note": "Modal smoke final in viz bundle",
            "summary": (
                "RFdiffusion3 bootstrap + Boltz-2-conditioned ProteinMPNN cycling on 4RWS."
            ),
        },
        "ligandmpnn-enzyme-redesign": {
            "domain": "Enzyme redesign",
            "primary_program": "design_001.py",
            "tool_chain": "LigandMPNN active-site MCMC",
            "sai_note": "LigandMPNN + Boltz-2 per proposal",
            "summary": (
                "Redesign active-site residues of holo enzyme 3HTB with LigandMPNN."
            ),
        },
        "bioemu-ensemble-filter": {
            "domain": "Protein ensemble",
            "primary_program": "design_001.py",
            "tool_chain": "BioEmu ensemble RMSD filter",
            "sai_note": "Batch BioEmu samples before learned fusion",
            "summary": (
                "BioEmu ensemble RMSD filter against 2LYZ; MCMC proxy for cycling loops."
            ),
        },
    }

    def load_collections() -> pd.DataFrame:
        rows: list[dict[str, object]] = []
        for manifest_path in sorted((REPO / "proto_programs/generated").glob("*/collection.json")):
            payload = json.loads(manifest_path.read_text())
            collection_id = str(payload["collection_id"])
            meta = COLLECTION_META.get(collection_id, {})
            rows.append(
                {
                    "collection_id": collection_id,
                    "domain": meta.get("domain", "—"),
                    "primary_program": meta.get("primary_program", "design_001.py"),
                    "tool_chain": meta.get("tool_chain", "—"),
                    "reviewed": payload.get("reviewed", False),
                    "programs": len(payload.get("programs", [])),
                    "sai_note": meta.get("sai_note", ""),
                    "summary": meta.get(
                        "summary",
                        f"Reviewed={payload.get('reviewed', False)}; "
                        f"{len(payload.get('programs', []))} programs.",
                    ),
                }
            )
        return pd.DataFrame(rows)

    return COLLECTION_META, REPO, load_collections


@app.cell(hide_code=True)
def _(Path, load_collections):
    collections_df = load_collections()
    test_modules = len(list((Path(__file__).resolve().parents[1] / "tests").glob("test_*.py")))
    reviewed_collections = int(collections_df["reviewed"].sum()) if not collections_df.empty else 0

    return collections_df, reviewed_collections, test_modules


@app.cell(hide_code=True)
def _(mermaid_init, dedent, mo):
    runtime_flow = f"""
    {mermaid_init}
    flowchart TB
        userProgram["User Proto<br/>program"] --> optimize["protofuse.optimize()"]
        optimize --> match{{"Compatible<br/>registered fusion?"}}
        match -->|no| fullModel["Original<br/>full-model path"]
        match -->|yes| router["Selective<br/>router"]
        router -->|unsafe or OOD| fullModel
        router -->|safe| surrogate["Learned<br/>surrogate"]
    """
    pipeline_flow = f"""
    {mermaid_init}
    flowchart TB
        collections["Frozen<br/>collections"] --> analyze["protofuse analyze"]
        analyze --> trace["protofuse trace<br/>teacher.jsonl"]
        trace --> profile["fusion profile"]
        profile --> train["fusion train<br/>data/models/"]
        train --> calibrate["Calibrate gate<br/>reviewed=false"]
        calibrate --> bundle["Reviewed<br/>FusionBundle"]
        bundle --> optimize["Auto-discover<br/>at optimize()"]
    """
    mo.vstack(
        [
            mo.md(
                dedent(
                    """
                    # ProtoFuse — GXL Hackathon Progress

                    **Primary output:** a complete **learned-fusion pipeline** — analyze frozen
                    Proto programs, trace teacher outputs, train a multi-output surrogate,
                    calibrate a fail-closed gate, and apply it transparently via
                    `protofuse.optimize()`.
                    """
                )
            ),
            mo.mermaid(runtime_flow, theme="dark"),
            mo.md(
                dedent(
                    """
                    ### Runtime (shipped)

                    1. **Match** — `FusionBundle` checks step signatures, tool versions, config,
                       and semantics (`sai/signatures.py`, `sai/transform.py`).
                    2. **Transform** — compatible step groups are replaced transactionally with
                       parent validation preserved.
                    3. **Route** — `SelectiveRouter` uses the surrogate only when calibration
                       accepts the input; errors and OOD defer to the **full model group**.
                    4. **Discover** — `optimize()` lazily loads reviewed bundles from
                       `data/models/` (or `PROTOFUSE_BUNDLE_DIR`).

                    ### Pipeline (shipped on `origin/main`)

                    | Stage | CLI | Status |
                    |-------|-----|--------|
                    | Controlled import + signatures | `protofuse analyze` | Done |
                    | Append-only teacher traces | `protofuse trace` | Done |
                    | Call/proposal profiling | `protofuse fusion profile` | Done |
                    | Multi-output ensemble + calibration | `protofuse fusion train` | Done |
                    | Paired full vs fused evaluation | `protofuse fusion evaluate` | Done |
                    | Reviewed bundle registration | manifest `reviewed=true` | **Next gate** |

                    **Evidence so far:** four Modal smoke workloads have full-model summaries;
                    `custom-egfp-lung` has a regression pilot (1,198 train samples); visualization
                    bundle includes smoke finals for antibody, ESM2, RFdiffusion3+Boltz-2.
                    No surrogate is **`reviewed=true`** yet — `optimize()` still runs full models
                    until the first bundle passes scientific review.

                    **First scientific target:** `boltz2-state-sweep` (labelled RMSD vs 4GBY/4GBZ).
                    """
                )
            ),
            mo.mermaid(pipeline_flow, theme="dark"),
            mo.callout(
                mo.md(
                    "Merge **`origin/main`** (`bc58898`) for the full Sai implementation: "
                    "`analyzer`, `tracing`, `training`, `transform`, evaluation report, and "
                    "visualization bundle. Local branch is ahead on Phillip handoffs but has "
                    "not merged Sai's fusion pipeline yet."
                ),
                kind="info",
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(collections_df, mo, reviewed_collections, test_modules):
    mo.hstack(
        [
            mo.stat(label="Frozen collections", value=str(len(collections_df))),
            mo.stat(label="Reviewed collections", value=str(reviewed_collections)),
            mo.stat(label="Test modules", value=str(test_modules)),
        ],
        justify="start",
        gap=1.5,
    )
    return


@app.cell(hide_code=True)
def _():
    from protofuse.phillip.paper_profiles import load_all_paper_profiles, resolve_figure_path

    paper_profiles = load_all_paper_profiles(fetch_online=True)
    return load_all_paper_profiles, paper_profiles, resolve_figure_path


@app.cell(hide_code=True)
def _(REPO, collections_df, mo, paper_profiles, resolve_figure_path):
    def _bullet_block(title: str, items: list[str]) -> str:
        if not items:
            return ""
        body = "\n".join(f"- {item}" for item in items)
        return f"**{title}**\n\n{body}\n\n"

    accordion_items: dict[str, object] = {}
    for row in collections_df.sort_values("collection_id").itertuples(index=False):
        profile = paper_profiles[row.collection_id]
        reviewed = "yes" if row.reviewed else "no"
        sai_note = row.sai_note or "No special fusion note."
        title = f"{row.collection_id} — {row.domain}"

        doi_line = (
            f"[{profile.display_doi}]({profile.doi_link})"
            if profile.display_doi and profile.doi_link
            else f"`{profile.identifier or 'no registered DOI'}`"
        )
        abstract = profile.abstract or "_Publisher did not deposit an abstract via Crossref._"
        if profile.reference_note:
            abstract = f"{profile.reference_note}\n\n{abstract}"

        text = (
            f"### {profile.display_title}\n\n"
            f"**DOI / identifier:** {doi_line}\n\n"
            f"**Abstract**\n\n{abstract}\n\n"
            f"{row.summary}\n\n"
            f"- **Tool chain:** {row.tool_chain}\n"
            f"- **Primary program:** `{row.primary_program}` "
            f"({int(row.programs)} programs in the collection)\n"
            f"- **Reviewed:** {reviewed}\n"
            f"- **Sai note:** {sai_note}\n\n"
            f"{_bullet_block('What we replicated from the paper', profile.replicated)}"
            f"{_bullet_block('Simplifications in this handoff', profile.assumptions)}"
            f"{_bullet_block('Not replicated (yet)', profile.not_replicated)}"
        )

        blocks: list[object] = [mo.md(text)]

        if profile.approved_figure_id:
            approved = next(
                (
                    candidate
                    for candidate in profile.figure_candidates
                    if candidate.figure_id == profile.approved_figure_id
                ),
                None,
            )
            if approved is not None:
                figure_path = resolve_figure_path(approved)
                src = str(figure_path) if figure_path else approved.url
                if src:
                    blocks.append(
                        mo.vstack(
                            [
                                mo.md(f"**Primary figure — {approved.label}**"),
                                mo.md(approved.caption),
                                mo.image(src=src),
                            ]
                        )
                    )

        accordion_items[title] = mo.vstack(blocks) if len(blocks) > 1 else blocks[0]

    mo.vstack(
        [
            mo.md("## Frozen program collections"),
            mo.md(
                "Handoff artifacts with source paper context — title, DOI, abstract, and "
                "what we replicated. Primary figures are added after curation."
            ),
            mo.accordion(accordion_items, multiple=True),
            mo.callout(
                mo.md(
                    "**Recommended fusion target:** `boltz2-state-sweep` — Boltz-2 sweep with "
                    "labelled RMSD ground truth (4GBY / 4GBZ)."
                ),
                kind="info",
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mermaid_init, dedent, mo):
    smoke_flow = f"""
    {mermaid_init}
    flowchart TB
        subgraph cpu ["Local CPU smoke"]
            direction TB
            dnaRun["protofuse run<br/>--tier smoke"]
            dnaCheck["Tiny sequence<br/>one loop pass"]
            dnaRun --> dnaCheck
        end
        subgraph gpu ["Modal GPU smoke"]
            direction TB
            modalRun["program.run()<br/>on Modal"]
            gpuCheck["Few MCMC steps<br/>short construct"]
            modalRun --> gpuCheck
        end
        goal["Prove tool<br/>bindings execute"]
        dnaCheck --> goal
        gpuCheck --> goal
    """
    mo.vstack(
        [
            mo.md(
                dedent(
                    """
                    ## What is a smoke test?

                    A **smoke test** is one deliberately **truncated** `program.run()` per
                    collection. It answers: *do the Proto bindings call the right tools and
                    return a result?* It is **not** paper-scale performance and **not** fusion
                    training data.

                    | Tier | Purpose | Owner |
                    |------|---------|-------|
                    | **Smoke** | Wiring check — tiny inputs, one end-to-end run | Phillip handoff gate |
                    | **Full** | Real loops, teacher traces, fusion profiling | Sai |

                    **Before GPU workflows**, smoke catches import errors, bad constraints, and
                    Modal misconfiguration before burning H100 hours. CPU collections smoke
                    locally; protein collections smoke on Modal with cut-down step counts.
                    """
                )
            ),
            mo.mermaid(smoke_flow, theme="dark"),
        ]
    )
    return


if __name__ == "__main__":
    app.run()
