"use client";

import {
  Activity,
  ArrowRight,
  Check,
  ChevronDown,
  CircleAlert,
  Clock3,
  Database,
  FlaskConical,
  Gauge,
  GitCompareArrows,
  HardDriveDownload,
  Layers3,
  Route,
  ShieldCheck,
  Sparkles,
  Target,
  X,
} from "lucide-react";
import { useMemo, useState } from "react";
import {
  auditDate,
  benchmarks,
  heldOutRows,
  measurementGroups,
  traceRows,
  type RunStatus,
} from "./evaluation-data";

type View = "readout" | "runs" | "evals";
type RunFilter = "all" | RunStatus;

const formatTime = (seconds: number) => {
  if (seconds < 10) return `${seconds.toFixed(3)} s`;
  if (seconds < 60) return `${seconds.toFixed(1)} s`;
  return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
};

const StatusPill = ({ state }: { state: "available" | "partial" | "missing" }) => (
  <span className={`state-pill ${state}`}>
    {state === "available" ? <Check size={13} /> : state === "partial" ? <CircleAlert size={13} /> : <X size={13} />}
    {state}
  </span>
);

export function EvaluationDashboard() {
  const [view, setView] = useState<View>("readout");
  const [runFilter, setRunFilter] = useState<RunFilter>("all");
  const [expandedRun, setExpandedRun] = useState<string | null>("custom-full");

  const visibleRuns = useMemo(
    () => benchmarks.filter((run) => runFilter === "all" || run.status === runFilter),
    [runFilter],
  );

  const scrollTo = (id: string) => {
    setView(id === "benchmarks" ? "runs" : id === "eval-plan" ? "evals" : "readout");
    requestAnimationFrame(() => document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" }));
  };

  return (
    <main>
      <header className="topbar">
        <button className="brand" onClick={() => scrollTo("top")} aria-label="Back to dashboard top">
          <span className="brand-mark"><Layers3 size={18} /></span>
          <span>PROTOFUSE</span>
          <span className="brand-slash">/</span>
          <span className="brand-muted">EVAL READOUT</span>
        </button>
        <nav aria-label="Dashboard sections">
          {(["readout", "runs", "evals"] as View[]).map((item) => (
            <button
              key={item}
              className={view === item ? "active" : ""}
              onClick={() => scrollTo(item === "readout" ? "readout" : item === "runs" ? "benchmarks" : "eval-plan")}
            >
              {item}
            </button>
          ))}
        </nav>
        <div className="audit-stamp"><span className="live-dot" /> audited {auditDate}</div>
      </header>

      <section className="hero" id="top">
        <div className="eyebrow"><FlaskConical size={15} /> evaluation readiness / current repository state</div>
        <div className="hero-grid">
          <div>
            <h1>We can measure speed.<br /><span>We cannot yet claim fusion.</span></h1>
            <p className="lede">The full-model baselines run, and supported optimizer units can now resume from crash-safe checkpoints. One CPU pilot reproduces two simple objectives. Eval-grade teacher traces, balanced held-out routing sets, registered surrogates, and paired GPU comparisons are still missing.</p>
            <div className="hero-actions">
              <button className="primary-action" onClick={() => scrollTo("benchmarks")}>Inspect run evidence <ArrowRight size={16} /></button>
              <button className="text-action" onClick={() => scrollTo("eval-plan")}>See the eval contract</button>
            </div>
          </div>
          <aside className="verdict-card">
            <div className="verdict-label">Current verdict</div>
            <div className="verdict-value">NOT READY</div>
            <p>for a paper-comparable full vs fused claim</p>
            <div className="verdict-rule" />
            <div className="verdict-detail"><Check size={15} /> full-model smoke baselines exist</div>
            <div className="verdict-detail"><Check size={15} /> optimizer checkpoints verified</div>
            <div className="verdict-detail warning"><CircleAlert size={15} /> fused GPU comparisons do not</div>
          </aside>
        </div>
      </section>

      <section className="metric-strip" id="readout" aria-label="Current audit metrics">
        <article title="A single analysis-only least-squares surrogate predicts tissue codon score and GC fraction.">
          <div className="metric-icon"><Sparkles size={18} /></div>
          <div className="metric-value">1 <span>/ 0</span></div>
          <div className="metric-name">experimental / registered surrogates</div>
        </article>
        <article title="One experimental coefficient matrix jointly predicts two objectives; none is deployed.">
          <div className="metric-icon"><GitCompareArrows size={18} /></div>
          <div className="metric-value">1 <span>× 2</span></div>
          <div className="metric-name">joint pilot × objectives</div>
        </article>
        <article title="Four hand-crafted OOD examples exist. There are no held-out high-value positive cases.">
          <div className="metric-icon"><ShieldCheck size={18} /></div>
          <div className="metric-value">4 <span>/ 0</span></div>
          <div className="metric-name">negative / positive challenges</div>
        </article>
        <article title="Constraint entries with at least one evidence record across all methodology fixtures.">
          <div className="metric-icon"><Database size={18} /></div>
          <div className="metric-value">21 <span>/ 51</span></div>
          <div className="metric-name">constraints with evidence</div>
        </article>
      </section>

      <section className="checkpoint-band" aria-label="Checkpoint readiness">
        <div className="checkpoint-title"><HardDriveDownload size={20} /><div><span>RESUME SAFETY</span><strong>Checkpointing is implemented and tested</strong></div></div>
        <div><span>Save boundary</span><strong>completed step / paid batch</strong></div>
        <div><span>Representative interruption</span><strong>2 saved · 3 resumed · 0 repeated</strong></div>
        <div><span>Coverage</span><strong>MCMC · cycling · rejection</strong></div>
        <div><span>Changed program</span><strong>fails closed</strong></div>
      </section>

      <section className="section-shell">
        <div className="section-heading">
          <div><span className="section-index">01</span><h2>Trace coverage</h2></div>
          <p>Can today’s artifacts be replayed as eval cases?</p>
        </div>
        <div className="trace-grid">
          {traceRows.map((row) => (
            <article className="trace-row" key={row.layer}>
              <div className="trace-glyph">{row.state === "available" ? <HardDriveDownload size={17} /> : row.state === "partial" ? <Activity size={17} /> : <Route size={17} />}</div>
              <div className="trace-copy"><h3>{row.layer}</h3><p>{row.detail}</p></div>
              <StatusPill state={row.state} />
            </article>
          ))}
        </div>
        <div className="callout"><CircleAlert size={18} /><p><strong>Bottom line:</strong> yes for a durable completion ledger and exact resume state; no for eval-ready traces of every model interaction. Raw parent outputs, objective components, surrogate predictions, routing decisions, and latency/cost still need the proposal schema below.</p></div>
      </section>

      <section className="section-shell split-section">
        <div className="section-heading">
          <div><span className="section-index">02</span><h2>Training & held-out sets</h2></div>
          <p>What exists is one leakage-limited pilot, not a training platform.</p>
        </div>
        <div className="training-layout">
          <article className="method-card">
            <div className="card-kicker">ONLY TRAINED PILOT</div>
            <h3>CUSTOM joint linear surrogate</h3>
            <p>68 codon/base-frequency features → one ordinary least-squares coefficient matrix → tissue score and GC fraction.</p>
            <div className="method-flow">
              <span>68 features</span><ArrowRight size={15} /><span>OLS</span><ArrowRight size={15} /><span>2 outputs</span>
            </div>
            <dl>
              <div><dt>Split unit</dt><dd>trajectory chain</dd></div>
              <div><dt>Split rule</dt><dd>chain_id mod 5</dd></div>
              <div><dt>Weights saved</dt><dd>no</dd></div>
              <div><dt>Gate deployed</dt><dd>no</dd></div>
            </dl>
          </article>
          <div className="cohort-table" role="table" aria-label="Held-out evaluation cohorts">
            <div className="cohort-header" role="row"><span>Cohort</span><span>N</span><span>Coverage</span><span>Status</span></div>
            {heldOutRows.map((row) => (
              <div className="cohort-row" role="row" key={row.cohort}>
                <strong>{row.cohort}</strong><span className="mono">{row.count}</span><span>{row.coverage}</span><span className={`cohort-verdict ${row.verdict}`}>{row.verdict}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="section-shell" id="benchmarks">
        <div className="section-heading benchmark-heading">
          <div><span className="section-index">03</span><h2>Full vs fused evidence</h2></div>
          <div className="filter-group" aria-label="Filter benchmark runs">
            {(["all", "paired", "baseline", "missing"] as RunFilter[]).map((filter) => (
              <button key={filter} className={runFilter === filter ? "active" : ""} onClick={() => setRunFilter(filter)}>{filter}</button>
            ))}
          </div>
        </div>
        <div className="paper-warning"><Target size={18} /><div><strong>Paper parity is not established.</strong><span>Only 3 of 12 fixtures point to paper text; 9 point to an internal candidate-workflow document. Current “final energy” values are internal composites, not error versus a paper-reported score.</span></div></div>
        <div className="benchmark-table">
          <div className="benchmark-header"><span>Workload</span><span>Work</span><span>Full</span><span>Fused</span><span>Objective error</span><span /></div>
          {visibleRuns.length === 0 ? <div className="empty-state">No runs match this filter.</div> : visibleRuns.map((run) => (
            <div className="benchmark-block" key={run.id}>
              <button className="benchmark-row" onClick={() => setExpandedRun(expandedRun === run.id ? null : run.id)} aria-expanded={expandedRun === run.id}>
                <span className="workload"><strong>{run.workload}</strong><small>{run.tier}</small></span>
                <span>{run.work}</span>
                <span className="timing"><Clock3 size={14} /> {formatTime(run.fullSeconds)}</span>
                <span>{run.fusedSeconds === null ? <em className="not-run">not run</em> : <span className="timing good"><Gauge size={14} /> {formatTime(run.fusedSeconds)}</span>}</span>
                <span className={run.status === "paired" ? "error-good" : "error-missing"}>{run.objectiveError}</span>
                <ChevronDown size={17} className={expandedRun === run.id ? "rotate" : ""} />
              </button>
              {expandedRun === run.id && (
                <div className="benchmark-detail">
                  <div><span>Objective</span><strong>{run.objective}</strong></div>
                  <div><span>Interpretation</span><strong>{run.note}</strong></div>
                  {run.speedup && <div><span>Observed speedup</span><strong>{run.speedup.toFixed(3)}×</strong></div>}
                </div>
              )}
            </div>
          ))}
        </div>
      </section>

      <section className="section-shell" id="eval-plan">
        <div className="section-heading">
          <div><span className="section-index">04</span><h2>Minimum eval contract</h2></div>
          <p>Record these before the next full/fused paired run.</p>
        </div>
        <div className="measurement-grid">
          {measurementGroups.map((group, index) => (
            <article className="measurement-card" key={group.title}>
              <div className="measurement-number">0{index + 1}</div><h3>{group.title}</h3>
              <ul>{group.items.map((item) => <li key={item}><Check size={14} />{item}</li>)}</ul>
            </article>
          ))}
        </div>
        <div className="trace-schema">
          <div><Database size={19} /><h3>One durable row per proposal</h3></div>
          <p>run + program/methodology hashes · paper objective version · seed · step · input hash · parent output · surrogate output · uncertainty · gate threshold · route/defer reason · decision · latency/GPU/cost · error · final validation</p>
        </div>
      </section>

      <footer><span>PROTOFUSE EVALUATION READOUT</span><span>Missing values are labeled, never treated as zero.</span></footer>
    </main>
  );
}
