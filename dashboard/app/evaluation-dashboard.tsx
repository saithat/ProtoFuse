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
  Pause,
  Play,
  RefreshCw,
  Route,
  ShieldCheck,
  Sparkles,
  Target,
  X,
} from "lucide-react";
import { useEffect, useMemo, useState, useSyncExternalStore } from "react";
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

const flowSteps = [
  {
    kicker: "01 / exact match",
    title: "Match only what is identical",
    detail: "ProtoFuse checks the optimizer position, component versions, configuration, inputs, outputs, thresholds, weights, and stochastic behavior. If any part differs, the original program stays untouched.",
    signal: "No match → original program",
  },
  {
    kicker: "02 / safe transform",
    title: "Replace one score-only group",
    detail: "A compatible program is deep-copied, then only the matched group is replaced. The change is transactional: a failed transformation cannot partially alter the user’s program.",
    signal: "One bounded replacement",
  },
  {
    kicker: "03 / per-input routing",
    title: "Route every input independently",
    detail: "Supported, confident inputs use the surrogate. Uncertain, out-of-distribution, unsupported, or failed inputs are batched back through the complete original model group.",
    signal: "Fast path + full-model fallback",
  },
  {
    kicker: "04 / final validation",
    title: "Finish with the original objectives",
    detail: "After optimization selects an output, the original matched objectives run again immediately. A bundle that asks for weaker final validation is rejected before use.",
    signal: "Original model has the last word",
  },
] as const;

const subscribeToReducedMotion = (onChange: () => void) => {
  const query = window.matchMedia("(prefers-reduced-motion: reduce)");
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
};

const getReducedMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

function SystemFlowExplainer() {
  const [activeStep, setActiveStep] = useState(0);
  const [isPlaying, setIsPlaying] = useState(true);
  const prefersReducedMotion = useSyncExternalStore(subscribeToReducedMotion, getReducedMotion, () => false);
  const isAutoPlaying = isPlaying && !prefersReducedMotion;

  useEffect(() => {
    if (!isAutoPlaying) return;
    const timer = window.setInterval(() => setActiveStep((step) => (step + 1) % flowSteps.length), 3600);
    return () => window.clearInterval(timer);
  }, [isAutoPlaying]);

  const chooseStep = (index: number) => {
    setActiveStep(index);
    setIsPlaying(false);
  };

  const step = flowSteps[activeStep];

  return (
    <section className="section-shell system-section" id="system-flow">
      <div className="section-heading system-heading">
        <div><span className="section-index">00</span><h2>How ProtoFuse works</h2></div>
        <p>A four-step, fail-closed path from ordinary program to validated output.</p>
      </div>

      <div className="system-explainer">
        <aside className="flow-story" aria-live="polite">
          <div className="story-topline">
            <span>{step.kicker}</span>
            <button
              type="button"
              className="play-toggle"
              onClick={() => setIsPlaying((playing) => !playing)}
              disabled={prefersReducedMotion}
              aria-label={prefersReducedMotion ? "System flow animation disabled by reduced motion preference" : isPlaying ? "Pause system flow animation" : "Play system flow animation"}
            >
              {isAutoPlaying ? <Pause size={14} /> : <Play size={14} />}
              {prefersReducedMotion ? "Motion off" : isPlaying ? "Pause" : "Play"}
            </button>
          </div>
          <div className="story-number">0{activeStep + 1}</div>
          <h3>{step.title}</h3>
          <p>{step.detail}</p>
          <div className="story-signal"><ShieldCheck size={15} />{step.signal}</div>
        </aside>

        <div className={`system-canvas step-${activeStep}`} aria-label="Animated diagram of the ProtoFuse runtime">
          <div className="canvas-label"><Activity size={14} /> LIVE RUNTIME PATH</div>
          <div className="source-row">
            <article className={`flow-node source-node ${activeStep === 0 ? "active" : ""}`}>
              <span className="node-icon"><Layers3 size={18} /></span>
              <div><small>USER INPUT</small><strong>Ordinary Proto program</strong></div>
            </article>
            <div className={`flow-link ${activeStep === 0 ? "active" : ""}`} aria-hidden="true"><span /></div>
            <article className={`flow-node match-node ${activeStep === 0 ? "active" : ""}`}>
              <span className="node-icon"><GitCompareArrows size={18} /></span>
              <div><small>STATIC CHECK</small><strong>Exact compatibility match</strong></div>
            </article>
            <div className={`flow-link ${activeStep === 1 ? "active" : ""}`} aria-hidden="true"><span /></div>
            <article className={`flow-node copy-node ${activeStep === 1 ? "active" : ""}`}>
              <span className="node-icon"><RefreshCw size={18} /></span>
              <div><small>TRANSACTIONAL COPY</small><strong>Replace matched score group</strong></div>
            </article>
          </div>

          <div className={`fallback-rail ${activeStep === 0 ? "active" : ""}`}>
            <span>No exact match</span><ArrowRight size={14} /><strong>return original program unchanged</strong>
          </div>

          <div className={`vertical-flow ${activeStep === 2 ? "active" : ""}`} aria-hidden="true"><span /></div>

          <article className={`flow-node router-node ${activeStep === 2 ? "active" : ""}`}>
            <span className="node-icon"><Route size={19} /></span>
            <div><small>SELECTIVE ROUTER</small><strong>Support distance + disagreement gates</strong></div>
            <div className="input-packets" aria-hidden="true">
              <span className="packet accepted">A1</span>
              <span className="packet fallback">B7</span>
              <span className="packet accepted">C4</span>
            </div>
          </article>

          <div className={`route-split ${activeStep === 2 ? "active" : ""}`} aria-hidden="true"><span /><i /><b /></div>
          <div className="route-options">
            <article className={`route-card surrogate-route ${activeStep === 2 ? "active" : ""}`}>
              <div className="route-card-top"><Sparkles size={17} /><span>SUPPORTED + CONFIDENT</span></div>
              <strong>Surrogate score vector</strong>
              <div className="route-meter"><span /></div>
              <small>Fast path</small>
            </article>
            <article className={`route-card original-route ${activeStep === 2 ? "active" : ""}`}>
              <div className="route-card-top"><FlaskConical size={17} /><span>UNCERTAIN · OOD · FAILED</span></div>
              <strong>Complete original model group</strong>
              <div className="route-meter"><span /></div>
              <small>Fail-closed path</small>
            </article>
          </div>

          <div className={`merge-flow ${activeStep === 3 ? "active" : ""}`} aria-hidden="true"><span /><i /><b /></div>
          <article className={`flow-node final-node ${activeStep === 3 ? "active" : ""}`}>
            <span className="node-icon"><ShieldCheck size={19} /></span>
            <div><small>MANDATORY FINAL STAGE</small><strong>Original objectives validate the selected output</strong></div>
            <span className="validation-stamp"><Check size={13} /> FULL MODEL</span>
          </article>
        </div>
      </div>

      <div className="flow-controls" aria-label="System flow steps">
        {flowSteps.map((item, index) => (
          <button
            type="button"
            key={item.kicker}
            className={activeStep === index ? "active" : ""}
            onClick={() => chooseStep(index)}
            aria-pressed={activeStep === index}
          >
            <span>0{index + 1}</span>
            <strong>{item.title}</strong>
            {activeStep === index && isAutoPlaying && <i key={`${activeStep}-${isAutoPlaying}`} aria-hidden="true" />}
          </button>
        ))}
      </div>
    </section>
  );
}

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
            <p className="lede">The full-model baselines run, and supported optimizer units can resume from crash-safe checkpoints. One local ten-trajectory diagnostic preserved final accuracy but produced no meaningful speedup. The other workloads still lack teacher traces, frozen external tests, registered surrogates, and paired learned-fusion runs.</p>
            <div className="hero-actions">
              <button className="primary-action" onClick={() => scrollTo("benchmarks")}>Inspect run evidence <ArrowRight size={16} /></button>
              <button className="text-action" onClick={() => scrollTo("eval-plan")}>See the eval contract</button>
            </div>
          </div>
          <aside className="verdict-card">
            <div className="verdict-label">Current verdict</div>
            <div className="verdict-value">NOT READY</div>
            <p>for a full multi-program fusion claim</p>
            <div className="verdict-rule" />
            <div className="verdict-detail"><Check size={15} /> full-model smoke baselines exist</div>
            <div className="verdict-detail"><Check size={15} /> optimizer checkpoints verified</div>
            <div className="verdict-detail warning"><CircleAlert size={15} /> fused GPU comparisons do not</div>
          </aside>
        </div>
      </section>

      <section className="metric-strip" id="readout" aria-label="Current audit metrics">
        <article title="One unreviewed tissue-only linear artifact was used for the paired local diagnostic.">
          <div className="metric-icon"><Sparkles size={18} /></div>
          <div className="metric-value">1 <span>/ 0</span></div>
          <div className="metric-name">experimental / registered surrogates</div>
        </article>
        <article title="Linear, tree, and small neural families were compared on a two-output development cohort; no joint winner was selected.">
          <div className="metric-icon"><GitCompareArrows size={18} /></div>
          <div className="metric-value">1 <span>× 2</span></div>
          <div className="metric-name">joint pilot × objectives</div>
        </article>
        <article title="The next protocol calls for 40–60 designed challenge cases; that cohort has not been collected.">
          <div className="metric-icon"><ShieldCheck size={18} /></div>
          <div className="metric-value">0 <span>/ 40–60</span></div>
          <div className="metric-name">collected / planned challenges</div>
        </article>
        <article title="Constraint entries with at least one evidence record across all methodology fixtures.">
          <div className="metric-icon"><Database size={18} /></div>
          <div className="metric-value">32 <span>/ 62</span></div>
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

      <SystemFlowExplainer />

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
        <div className="callout"><CircleAlert size={18} /><p><strong>Bottom line:</strong> CUSTOM now has one teacher trace and one aggregate paired report. The other workloads still lack those records, and surrogate predictions, routing decisions, and parent recovery are not yet joined into one durable proposal-level campaign trace.</p></div>
      </section>

      <section className="section-shell split-section">
        <div className="section-heading">
          <div><span className="section-index">02</span><h2>Training & held-out sets</h2></div>
          <p>The current ten-trajectory pilot can reject weak ideas, but it cannot establish generalization.</p>
        </div>
        <div className="trajectory-guide" aria-label="How optimizer trajectories become model splits">
          <article>
            <span>01 · RUN</span>
            <strong>One seed creates one trajectory</strong>
            <p>A complete optimizer run produces a sequence of proposals. Later proposals depend on earlier accept/reject decisions.</p>
          </article>
          <ArrowRight size={18} aria-hidden="true" />
          <article>
            <span>02 · GROUP</span>
            <strong>Many rows remain one unit</strong>
            <p>Constraint rows for a proposal become one aligned teacher sample, but every sample from that trajectory keeps the same group ID.</p>
          </article>
          <ArrowRight size={18} aria-hidden="true" />
          <article>
            <span>03 · SPLIT</span>
            <strong>Assign complete trajectories</strong>
            <p>Whole groups—not shuffled proposal rows—go to train, calibration, or test. This prevents neighboring optimizer states from leaking.</p>
          </article>
        </div>
        <div className="trajectory-target">
          <div><span>PREFERRED COLLECTION</span><strong>60 train + 20 calibration + 20 untouched test trajectories</strong></div>
          <p>At 20 proposals per run this is about 1,200/400/400 model samples, but the independent counts remain 60/20/20. Keep roughly 50 additional trajectories for paired timing and 40–60 designed challenge cases.</p>
        </div>
        <div className="training-layout">
          <article className="method-card">
            <div className="card-kicker">CURRENT DEVELOPMENT PILOT</div>
            <h3>CUSTOM trajectory split</h3>
            <p>Ten seeded runs produced 200 aligned proposal states. Linear, tree, and small neural models saw the same grouped split.</p>
            <div className="method-flow">
              <span>10 trajectories</span><ArrowRight size={15} /><span>200 states</span><ArrowRight size={15} /><span>6 / 2 / 2 groups</span>
            </div>
            <dl>
              <div><dt>Split unit</dt><dd>complete trajectory</dd></div>
              <div><dt>Group allocation</dt><dd>60% / 20% / 20%</dd></div>
              <div><dt>Effective independent N</dt><dd>6 / 2 / 2</dd></div>
              <div><dt>Artifact decision</dt><dd>unreviewed · rejected</dd></div>
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
        <p className="split-warning"><strong>Untouched means untouched:</strong> because the current audit results were inspected while comparing model families, those two trajectories are now development data. A final claim needs a newly frozen external test cohort.</p>
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
        <div className="paper-warning"><Target size={18} /><div><strong>Paper parity is not established.</strong><span>Three of 15 fixtures point to paper-specific local text, nine use the internal candidate-workflow document, and three declare no local source. Current “final energy” values are internal composites, not error versus a paper-reported score.</span></div></div>
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
