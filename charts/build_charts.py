"""Build slide-ready, evidence-backed ProtoFuse research charts."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.patches import Patch

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ANALYSIS_ROOT = REPO_ROOT / "data" / "analysis"
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent

COLORS = {
    "adaptive": "#0F766E",
    "sampled": "#D97706",
    "parallel": "#2563EB",
    "surrogate": "#0F766E",
    "fallback": "#9CA3AF",
    "exact_parallel": "#2563EB",
    "pass": "#059669",
    "threshold": "#334155",
    "ink": "#172033",
    "muted": "#58677C",
    "grid": "#D8DEE9",
    "background": "#FFFFFF",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--analysis-root",
        type=Path,
        default=DEFAULT_ANALYSIS_ROOT,
        help="Directory containing aggregate evaluation artifacts.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Destination for PNG, SVG, and source-data.json files.",
    )
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"Required aggregate result is missing: {path}")
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def nested_number(data: dict[str, Any], *keys: str) -> float:
    value: Any = data
    for key in keys:
        if not isinstance(value, dict) or key not in value:
            raise ValueError(f"Missing required field: {'.'.join(keys)}")
        value = value[key]
    if not isinstance(value, int | float):
        raise ValueError(f"Expected a number at: {'.'.join(keys)}")
    return float(value)


def nested_int(data: dict[str, Any], *keys: str) -> int:
    value = nested_number(data, *keys)
    if not value.is_integer():
        raise ValueError(f"Expected an integer at: {'.'.join(keys)}")
    return int(value)


def relative_source(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path.resolve())


def style() -> None:
    plt.rcParams.update(
        {
            "figure.facecolor": COLORS["background"],
            "axes.facecolor": COLORS["background"],
            "axes.edgecolor": COLORS["grid"],
            "axes.labelcolor": COLORS["ink"],
            "axes.titlecolor": COLORS["ink"],
            "axes.titlesize": 22,
            "axes.titleweight": "bold",
            "font.family": "DejaVu Sans",
            "font.size": 13,
            "text.color": COLORS["ink"],
            "xtick.color": COLORS["muted"],
            "ytick.color": COLORS["ink"],
            "legend.frameon": False,
            "svg.fonttype": "none",
        }
    )


def new_figure() -> tuple[Figure, Axes]:
    return plt.subplots(figsize=(12, 6.75))


def save_figure(fig: Figure, output_dir: Path, stem: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_dir / f"{stem}.png", dpi=200, facecolor=COLORS["background"])
    fig.savefig(output_dir / f"{stem}.svg", facecolor=COLORS["background"])
    plt.close(fig)


def simplify_axes(ax: Axes) -> None:
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.tick_params(axis="both", length=0)
    ax.set_axisbelow(True)
    ax.grid(axis="x", color=COLORS["grid"], linewidth=0.9)


def build_speedup_fidelity(strategies: list[dict[str, Any]], output_dir: Path) -> None:
    fig, ax = new_figure()
    fig.subplots_adjust(left=0.2, right=0.96, top=0.79, bottom=0.2)
    positions = list(range(len(strategies)))
    values = [float(item["net_speedup"]) for item in strategies]
    errors = [
        [
            value - float(item["speedup_ci_95"][0])
            for item, value in zip(strategies, values, strict=True)
        ],
        [
            float(item["speedup_ci_95"][1]) - value
            for item, value in zip(strategies, values, strict=True)
        ],
    ]
    colors = [COLORS[str(item["color"])] for item in strategies]

    ax.barh(positions, values, height=0.58, color=colors, zorder=3)
    ax.errorbar(
        values,
        positions,
        xerr=errors,
        fmt="none",
        ecolor=COLORS["ink"],
        elinewidth=1.6,
        capsize=4,
        zorder=4,
    )
    ax.axvline(1.0, color=COLORS["muted"], linewidth=1.4, linestyle="--")
    ax.text(1.15, -0.43, "1x full path", ha="left", color=COLORS["muted"], fontsize=11)

    for position, value, item in zip(positions, values, strategies, strict=True):
        recall = float(item["mean_top10_recall"])
        minimum = float(item["minimum_top10_recall"])
        recall_text = f"top-10 {recall:.0%}"
        if minimum < recall:
            recall_text += f" mean ({minimum:.0%} min)"
        ax.text(
            value + 0.22,
            position,
            f"{value:.2f}x\n{recall_text}",
            va="center",
            ha="left",
            fontsize=11.5,
            fontweight="bold",
            color=COLORS["ink"],
        )

    ax.set_yticks(positions, [str(item["label"]) for item in strategies])
    ax.invert_yaxis()
    ax.set_xlim(0, 19)
    ax.set_xlabel("Net end-to-end speedup (x)", labelpad=12)
    fig.suptitle(
        "Speed–fidelity tradeoff in eGFP optimization",
        x=0.2,
        y=0.95,
        ha="left",
        fontsize=22,
        fontweight="bold",
    )
    fig.text(
        0.2,
        0.035,
        "Paired local-CPU cohorts; whiskers are bootstrap 95% confidence intervals.\n"
        "Exact parallel uses 8 workers and avoids no scientific calculations.",
        fontsize=11,
        color=COLORS["muted"],
        ha="left",
    )
    simplify_axes(ax)
    save_figure(fig, output_dir, "01-speedup-fidelity")


def build_routing_composition(routing_rows: list[dict[str, Any]], output_dir: Path) -> None:
    fig, ax = new_figure()
    fig.subplots_adjust(left=0.25, right=0.96, top=0.73, bottom=0.2)
    positions = list(range(len(routing_rows)))
    categories = (
        ("surrogate_routes", "Surrogate", COLORS["surrogate"]),
        ("fallback_routes", "Exact fallback", COLORS["fallback"]),
        ("exact_parallel_routes", "Exact parallel", COLORS["exact_parallel"]),
    )
    left = [0.0] * len(routing_rows)

    for field, label, color in categories:
        widths = [100 * int(row[field]) / int(row["total_routes"]) for row in routing_rows]
        ax.barh(positions, widths, left=left, height=0.6, color=color, zorder=3)
        for index, (start, width, row) in enumerate(zip(left, widths, routing_rows, strict=True)):
            count = int(row[field])
            if width >= 8:
                text_color = "#FFFFFF" if field != "fallback_routes" else COLORS["ink"]
                ax.text(
                    start + width / 2,
                    index,
                    f"{width:.1f}%\n(n={count:,})",
                    ha="center",
                    va="center",
                    fontsize=11,
                    fontweight="bold",
                    color=text_color,
                )
            elif count > 0:
                ax.text(
                    101.5,
                    index,
                    f"{label.lower()} {width:.1f}% (n={count:,})",
                    ha="left",
                    va="center",
                    fontsize=10.5,
                    color=COLORS["ink"],
                )
        left = [start + width for start, width in zip(left, widths, strict=True)]

    ax.set_yticks(positions, [str(row["label"]) for row in routing_rows])
    ax.invert_yaxis()
    ax.set_xlim(0, 130)
    ax.set_xticks([0, 25, 50, 75, 100], ["0%", "25%", "50%", "75%", "100%"])
    ax.set_xlabel("Routing decisions", labelpad=12)
    fig.suptitle(
        "Fail-closed routing by workload",
        x=0.25,
        y=0.95,
        ha="left",
        fontsize=22,
        fontweight="bold",
    )
    ax.legend(
        handles=[Patch(facecolor=color, label=label) for _, label, color in categories],
        loc="lower left",
        bbox_to_anchor=(0, 1.04),
        ncol=3,
        fontsize=12,
    )
    fig.text(
        0.25,
        0.035,
        "Supported CUSTOM inputs use a surrogate; unsupported Evo2 inputs are fully deferred.\n"
        "Evo2 is one independent scaled audit, not an acceleration result.",
        fontsize=11,
        color=COLORS["muted"],
        ha="left",
    )
    simplify_axes(ax)
    save_figure(fig, output_dir, "02-routing-composition")


def build_audit_gates(audit: dict[str, Any], output_dir: Path) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(12, 6.75))
    fig.subplots_adjust(left=0.06, right=0.98, top=0.76, bottom=0.23, wspace=0.08)
    panels = [
        {
            "title": "Accepted normalized MAE",
            "observed": 100 * float(audit["accepted_mae_q95_q05_fraction"]),
            "threshold": 100 * float(audit["max_accepted_mae_q95_q05_fraction"]),
            "maximum": 6.0,
            "unit": "% of held-out range",
            "direction": "lower",
        },
        {
            "title": "Accepted rank correlation",
            "observed": float(audit["accepted_spearman"]),
            "threshold": float(audit["min_accepted_spearman"]),
            "maximum": 1.0,
            "unit": "Spearman rho",
            "direction": "higher",
        },
        {
            "title": "Selective coverage",
            "observed": 100 * float(audit["coverage"]),
            "threshold": 100 * float(audit["min_coverage"]),
            "maximum": 100.0,
            "unit": "% of proposals",
            "direction": "higher",
        },
    ]

    for ax, panel in zip(axes, panels, strict=True):
        observed = float(panel["observed"])
        threshold = float(panel["threshold"])
        maximum = float(panel["maximum"])
        ax.barh([0], [observed], height=0.28, color=COLORS["pass"], zorder=3)
        ax.axvline(threshold, color=COLORS["threshold"], linewidth=2, linestyle="--", zorder=4)
        ax.set_xlim(0, maximum)
        ax.set_ylim(-0.8, 0.8)
        ax.set_yticks([])
        ax.set_title(str(panel["title"]), fontsize=15, pad=16)
        if panel["unit"] == "Spearman rho":
            observed_text = f"{observed:.3f}"
            threshold_text = f"floor {threshold:.2f}"
        else:
            observed_text = f"{observed:.1f}%"
            threshold_text = (
                f"ceiling {threshold:.1f}%"
                if panel["direction"] == "lower"
                else f"floor {threshold:.0f}%"
            )
        ax.text(
            observed,
            0.23,
            observed_text,
            ha="right" if observed > maximum * 0.18 else "left",
            va="bottom",
            color=COLORS["pass"],
            fontsize=17,
            fontweight="bold",
        )
        ax.text(
            threshold,
            -0.25,
            threshold_text,
            ha="center",
            va="top",
            color=COLORS["threshold"],
            fontsize=11,
        )
        ax.set_xlabel(str(panel["unit"]), labelpad=10)
        ax.spines[["top", "right", "left"]].set_visible(False)
        ax.tick_params(axis="both", length=0)
        ax.grid(axis="x", color=COLORS["grid"], linewidth=0.9)
        ax.set_axisbelow(True)

    fig.suptitle(
        "Frozen CUSTOM audit clears every declared gate",
        x=0.04,
        y=0.95,
        ha="left",
        fontsize=22,
        fontweight="bold",
    )
    fig.text(
        0.04,
        0.05,
        f"Four untouched groups · n={int(audit['total_samples']):,} proposals · "
        f"n={int(audit['accepted_samples']):,} accepted · frozen audit status: PASS",
        fontsize=11,
        color=COLORS["muted"],
        ha="left",
    )
    save_figure(fig, output_dir, "03-frozen-audit-gates")


def assemble_source_data(analysis_root: Path) -> dict[str, Any]:
    custom_root = analysis_root / "custom-egfp-lung"
    paths = {
        "adaptive": custom_root / "paired-adaptive-boundary-fresh-seeds-200-203.json",
        "sampled": custom_root / "paired-sampled-window.json",
        "parallel": custom_root / "paired-exact-parallel.json",
        "custom_audit": custom_root / "frozen-sampled-mfe-audit-v2.json",
        "evo2_audit": analysis_root
        / "evo2-enformer-borzoi"
        / "audit"
        / "design-006-seed-001-audit.json",
    }
    raw = {name: load_json(path) for name, path in paths.items()}

    require(
        raw["adaptive"].get("status") == "fresh_confirmation_pass",
        "Adaptive confirmation did not pass",
    )
    require(
        raw["adaptive"].get("all_final_sequences_identical") is True,
        "Adaptive final outputs differ",
    )
    require(
        raw["parallel"].get("all_final_sequences_identical") is True,
        "Exact-parallel final outputs differ",
    )
    require(raw["custom_audit"].get("passed") is True, "Frozen CUSTOM audit did not pass")
    require(raw["evo2_audit"].get("passed") is False, "Expected Evo2 audit to remain fail-closed")

    strategy_specs = [
        ("adaptive", "Adaptive boundary", "adaptive"),
        ("sampled", "Sampled window", "sampled"),
        ("parallel", "Exact parallel", "parallel"),
    ]
    strategies: list[dict[str, Any]] = []
    for key, label, color in strategy_specs:
        result = raw[key]
        ci = result["metrics"]["timing"]["speedup_bootstrap_95_ci"]
        recalls = [float(run["top_k_recall"]) for run in result["runs"]]
        strategies.append(
            {
                "id": key,
                "label": label,
                "color": color,
                "net_speedup": nested_number(result, "metrics", "timing", "net_speedup"),
                "speedup_ci_95": [float(ci[0]), float(ci[1])],
                "mean_top10_recall": nested_number(
                    result, "metrics", "accuracy", "mean_top_k_recall"
                ),
                "minimum_top10_recall": min(recalls),
                "paired_runs": nested_int(result, "metrics", "reliability", "paired_runs"),
                "proposals": nested_int(result, "metrics", "work", "proposals"),
            }
        )

    routing_rows = [
        {
            "label": "CUSTOM adaptive",
            "surrogate_routes": nested_int(
                raw["adaptive"], "metrics", "routing", "surrogate_routes"
            ),
            "fallback_routes": nested_int(
                raw["adaptive"], "metrics", "routing", "full_model_routes"
            ),
            "exact_parallel_routes": 0,
            "total_routes": nested_int(raw["adaptive"], "metrics", "work", "proposals"),
        },
        {
            "label": "CUSTOM sampled",
            "surrogate_routes": nested_int(
                raw["sampled"], "metrics", "routing", "surrogate_routes"
            ),
            "fallback_routes": nested_int(
                raw["sampled"], "metrics", "routing", "full_model_routes"
            ),
            "exact_parallel_routes": 0,
            "total_routes": nested_int(raw["sampled"], "metrics", "work", "proposals"),
        },
        {
            "label": "CUSTOM exact parallel",
            "surrogate_routes": 0,
            "fallback_routes": 0,
            "exact_parallel_routes": nested_int(
                raw["parallel"], "metrics", "routing", "exact_parallel_routes"
            ),
            "total_routes": nested_int(raw["parallel"], "metrics", "work", "proposals"),
        },
        {
            "label": "Evo2 independent audit",
            "surrogate_routes": nested_int(raw["evo2_audit"], "samples", "accepted"),
            "fallback_routes": nested_int(raw["evo2_audit"], "samples", "rejected"),
            "exact_parallel_routes": 0,
            "total_routes": nested_int(raw["evo2_audit"], "samples", "total"),
        },
    ]
    for row in routing_rows:
        require(
            int(row["surrogate_routes"])
            + int(row["fallback_routes"])
            + int(row["exact_parallel_routes"])
            == int(row["total_routes"]),
            f"Route counts do not sum for {row['label']}",
        )

    custom_audit = raw["custom_audit"]
    audit = {
        "accepted_mae_q95_q05_fraction": nested_number(
            custom_audit, "metrics", "accepted_mae_q95_q05_fraction"
        ),
        "max_accepted_mae_q95_q05_fraction": nested_number(
            custom_audit, "thresholds", "max_accepted_mae_q95_q05_fraction"
        ),
        "accepted_spearman": nested_number(custom_audit, "metrics", "accepted_spearman"),
        "min_accepted_spearman": nested_number(custom_audit, "thresholds", "min_accepted_spearman"),
        "coverage": nested_number(custom_audit, "samples", "coverage"),
        "min_coverage": nested_number(custom_audit, "thresholds", "min_coverage"),
        "total_samples": nested_int(custom_audit, "samples", "total"),
        "accepted_samples": nested_int(custom_audit, "samples", "accepted"),
        "heldout_groups": 4,
        "status": "pass",
    }

    return {
        "schema_version": "1.0",
        "scope": "Aggregate, slide-safe chart data; no proposal-level records or sequences.",
        "sources": {
            name: {"path": relative_source(path), "sha256": sha256(path)}
            for name, path in paths.items()
        },
        "strategies": strategies,
        "routing": routing_rows,
        "custom_frozen_audit": audit,
    }


def main() -> None:
    args = parse_args()
    style()
    source_data = assemble_source_data(args.analysis_root)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    with (args.output_dir / "source-data.json").open("w", encoding="utf-8") as handle:
        json.dump(source_data, handle, indent=2)
        handle.write("\n")

    build_speedup_fidelity(source_data["strategies"], args.output_dir)
    build_routing_composition(source_data["routing"], args.output_dir)
    build_audit_gates(source_data["custom_frozen_audit"], args.output_dir)


if __name__ == "__main__":
    main()
