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

    _box = (
        "border:1px solid #484f58;background:#161b22;color:#e6edf3;"
        "padding:10px 14px;border-radius:8px;white-space:nowrap;font-size:14px;"
    )
    _diamond = (
        "border:1px solid #484f58;background:#161b22;color:#e6edf3;"
        "padding:10px 12px;transform:rotate(45deg);width:92px;height:92px;"
        "display:flex;align-items:center;justify-content:center;font-size:13px;"
    )
    _diamond_text = "transform:rotate(-45deg);text-align:center;line-height:1.2;"
    _arrow = "color:#8b949e;font-size:20px;padding:0 8px;flex:0 0 auto;"
    _label = "color:#8b949e;font-size:12px;text-align:center;min-width:36px;"

    def flow_node(label: str) -> str:
        return f'<div style="{_box}">{label}</div>'

    def flow_diamond(label: str) -> str:
        inner = f'<span style="{_diamond_text}">{label}</span>'
        return f'<div style="{_diamond}">{inner}</div>'

    def flow_arrow(text: str = "→") -> str:
        return f'<div style="{_arrow}">{text}</div>'

    def flow_edge(label: str) -> str:
        return f'<div style="{_label}">{label}</div>'

    def runtime_flow_chart() -> mo.Html:
        return mo.Html(
            f"""
            <div style="display:flex;flex-direction:column;gap:12px;margin:8px 0 16px;">
              <div style="display:flex;flex-wrap:wrap;align-items:center;gap:4px;">
                {flow_node("User program")}
                {flow_arrow()}
                {flow_node("protofuse.optimize()")}
                {flow_arrow()}
                {flow_diamond("Fusion match?")}
                {flow_edge("yes")}
                {flow_arrow()}
                {flow_node("Selective router")}
                {flow_edge("accept")}
                {flow_arrow()}
                {flow_node("Learned surrogate")}
              </div>
              <div style="display:flex;flex-wrap:wrap;align-items:center;gap:4px;
                          padding-left:248px;">
                {flow_edge("no / reject")}
                {flow_arrow("↳")}
                {flow_node("Original full-model path")}
              </div>
            </div>
            """
        )

    def pipeline_flow_chart() -> mo.Html:
        steps = [
            "Frozen collections",
            "protofuse analyze",
            "protofuse trace",
            "fusion profile",
            "fusion train",
            "Calibrate gate",
            "Reviewed FusionBundle",
            "protofuse.optimize()",
        ]
        parts: list[str] = []
        for index, step in enumerate(steps):
            parts.append(flow_node(step))
            if index < len(steps) - 1:
                parts.append(flow_arrow())
        body = "".join(parts)
        return mo.Html(
            f"""
            <div style="display:flex;flex-wrap:wrap;align-items:center;gap:4px;margin:8px 0 16px;">
              {body}
            </div>
            """
        )

    def smoke_flow_chart() -> mo.Html:
        return mo.Html(
            f"""
            <div style="display:flex;flex-direction:column;gap:12px;margin:8px 0 16px;">
              <div style="display:flex;flex-wrap:wrap;align-items:center;gap:4px;">
                {flow_node("CPU: protofuse run --tier smoke")}
                {flow_arrow()}
                {flow_node("Tiny sequence, one pass")}
                {flow_arrow()}
                {flow_node("Bindings OK")}
              </div>
              <div style="display:flex;flex-wrap:wrap;align-items:center;gap:4px;">
                {flow_node("GPU: program.run() on Modal")}
                {flow_arrow()}
                {flow_node("Few MCMC steps, short construct")}
                {flow_arrow()}
                {flow_node("Bindings OK")}
              </div>
            </div>
            """
        )

    return (
        Path,
        dedent,
        json,
        mo,
        pd,
        pipeline_flow_chart,
        runtime_flow_chart,
        smoke_flow_chart,
    )


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

    return (load_collections,)


@app.cell(hide_code=True)
def _(Path, load_collections):
    collections_df = load_collections()
    test_modules = len(list((Path(__file__).resolve().parents[1] / "tests").glob("test_*.py")))
    reviewed_collections = int(collections_df["reviewed"].sum()) if not collections_df.empty else 0
    return collections_df, reviewed_collections, test_modules


@app.cell(hide_code=True)
def _(dedent, mo):
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
    )
    return


@app.cell(hide_code=True)
def _(collections_df, mo, reviewed_collections, test_modules):
    mo.hstack(
        [
            mo.stat(label="Programs", value=str(len(collections_df))),
            mo.stat(label="Reviewed collections", value=str(reviewed_collections)),
            mo.stat(label="Test modules", value=str(test_modules)),
        ],
        justify="start",
        gap=1.5,
    )
    return


@app.cell(hide_code=True)
def _():
    from protofuse.phillip.paper_profiles import (
        figure_image_src,
        load_all_paper_profiles,
        primary_figure,
    )

    paper_profiles = load_all_paper_profiles(fetch_online=False)
    return figure_image_src, paper_profiles, primary_figure


@app.cell(hide_code=True)
def _(collections_df, mo):
    collection_options = {
        f"{row.collection_id} — {row.domain}": row.collection_id
        for row in collections_df.sort_values("collection_id").itertuples(index=False)
    }
    default_option = next(iter(collection_options.keys()), None)
    collection_picker = mo.ui.dropdown(
        options=collection_options,
        label="Program collection",
        value=default_option,
    )
    overview = collections_df.sort_values("collection_id")[
        ["collection_id", "domain", "tool_chain", "reviewed"]
    ]
    mo.vstack(
        [
            mo.md("## Programs"),
            mo.md(
                "Handoff artifacts with source paper context — title, DOI, abstract, primary "
                "figure, and what we replicated. Select a collection to load its details."
            ),
            mo.ui.table(overview),
            collection_picker,
        ]
    )
    return collection_picker


@app.cell(hide_code=True)
def _(
    collection_picker,
    collections_df,
    figure_image_src,
    mo,
    paper_profiles,
    primary_figure,
):
    def _bullet_block(title: str, items: list[str]) -> str:
        if not items:
            return ""
        body = "\n".join(f"- {item}" for item in items)
        return f"**{title}**\n\n{body}\n\n"

    selected_id = collection_picker.value
    if not selected_id or selected_id not in paper_profiles:
        collection_detail = mo.md("_Select a collection above._")
    else:
        row = collections_df.loc[collections_df["collection_id"] == selected_id].iloc[0]
        profile = paper_profiles[selected_id]
        reviewed = "yes" if row.reviewed else "no"
        sai_note = row.sai_note or "No special fusion note."

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
        )

        blocks: list[object] = [mo.md(text)]

        figure = primary_figure(profile)
        if figure is not None:
            src = figure_image_src(figure)
            if src:
                blocks.append(
                    mo.vstack(
                        [
                            mo.md(f"**Primary figure — {figure.label}**"),
                            mo.image(src=src),
                        ]
                    )
                )

        blocks.append(
            mo.md(
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
        )

        if figure is not None and figure.caption:
            blocks.append(mo.md(f"*{figure.caption}*"))

        collection_detail = mo.vstack(
            [
                *blocks,
                mo.callout(
                    mo.md(
                        "**Recommended fusion target:** `boltz2-state-sweep` — Boltz-2 sweep with "
                        "labelled RMSD ground truth (4GBY / 4GBZ)."
                    ),
                    kind="info",
                ),
            ]
        )

    collection_detail  # noqa: B018 - final Marimo cell expression renders the component


@app.cell(hide_code=True)
def _(dedent, mo, pipeline_flow_chart, runtime_flow_chart):
    mo.vstack(
        [
            mo.md("## Runtime"),
            runtime_flow_chart(),
            mo.md(
                "*Runtime:* `protofuse.optimize()` → fusion match → selective router → "
                "surrogate (accept) or full models (reject / no match)."
            ),
            mo.md(
                dedent(
                    """
                    ### At execution (shipped)

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
            pipeline_flow_chart(),
            mo.md(
                "*Pipeline CLI:* `analyze` → `trace` → `fusion profile` → `fusion train` → "
                "reviewed bundle → auto-discover at `optimize()`."
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(dedent, mo, smoke_flow_chart):
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
                    | **Smoke** | Tiny-input wiring check; one end-to-end run | Phillip handoff |
                    | **Full** | Real loops, teacher traces, fusion profiling | Sai |

                    **Before GPU workflows**, smoke catches import errors, bad constraints, and
                    Modal misconfiguration before burning H100 hours. CPU collections smoke
                    locally; protein collections smoke on Modal with cut-down step counts.
                    """
                )
            ),
            smoke_flow_chart(),
        ]
    )
    return


if __name__ == "__main__":
    app.run()
