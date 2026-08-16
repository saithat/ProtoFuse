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
  const [expandedRun, setExpandedRun] = useState<string | null>("custom-adaptive-confirmation");

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
            <h1>One narrow path is confirmed.<br /><span>Broad fusion is not.</span></h1>
            <p className="lede">CUSTOM’s adaptive MFE path passed four fresh counterbalanced pairs at 9.72× net speedup, with identical candidate pools, exact selected outputs, and 100% top-10 recall. The joint LigandMPNN–ESMFold and scaled Evo2 surrogates failed their frozen audits, so those routes remain safely deferred rather than promoted.</p>
            <div className="hero-actions">
              <button className="primary-action" onClick={() => scrollTo("benchmarks")}>Inspect run evidence <ArrowRight size={16} /></button>
              <button className="text-action" onClick={() => scrollTo("eval-plan")}>See the eval contract</button>
            </div>
          </div>
          <aside className="verdict-card">
            <div className="verdict-label">Current verdict</div>
            <div className="verdict-value confirmed">NARROW PASS</div>
            <p>CUSTOM MFE confirmation passed; cross-program approval did not</p>
            <div className="verdict-rule" />
            <div className="verdict-detail"><Check size={15} /> 4 / 4 fresh CUSTOM pairs passed</div>
            <div className="verdict-detail"><Check size={15} /> exact top-10 recovery</div>
            <div className="verdict-detail warning"><CircleAlert size={15} /> 2 joint surrogate audits failed</div>
          </aside>
        </div>
      </section>

      <section className="metric-strip" id="readout" aria-label="Current audit metrics">
        <article title="Net end-to-end speedup across the four fresh CUSTOM confirmation pairs.">
          <div className="metric-icon"><Gauge size={18} /></div>
          <div className="metric-value">9.72<span>×</span></div>
          <div className="metric-name">CUSTOM confirmation speedup</div>
        </article>
        <article title="Every fresh counterbalanced pair completed with identical ordered candidate-pool hashes and exact top-10 recovery.">
          <div className="metric-icon"><GitCompareArrows size={18} /></div>
          <div className="metric-value">4 <span>/ 4</span></div>
          <div className="metric-name">fresh paired runs passed</div>
        </article>
        <article title="3,844 of 4,000 CUSTOM candidates used sampled MFE; 156 routed to exact MFE through uncertainty, boundary, or tail recovery.">
          <div className="metric-icon"><ShieldCheck size={18} /></div>
          <div className="metric-value">96.1<span>%</span></div>
          <div className="metric-name">selective surrogate coverage</div>
        </article>
        <article title="The LigandMPNN–ESMFold and scaled Evo2 artifacts both failed their frozen external approval audits.">
          <div className="metric-icon"><Database size={18} /></div>
          <div className="metric-value">2</div>
          <div className="metric-name">joint surrogate audits failed</div>
        </article>
      </section>

      <section className="checkpoint-band" aria-label="Fresh confirmation result">
        <div className="checkpoint-title"><ShieldCheck size={20} /><div><span>FRESH CONFIRMATION</span><strong>Adaptive CUSTOM MFE passed</strong></div></div>
        <div><span>Candidate pools</span><strong>4 / 4 identical</strong></div>
        <div><span>Top-10 recall</span><strong>1.00 mean · 1.00 minimum</strong></div>
        <div><span>Exact recovery</span><strong>156 routed candidates</strong></div>
        <div><span>Promotion</span><strong>review gates remain</strong></div>
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
        <div className="callout"><CircleAlert size={18} /><p><strong>Bottom line:</strong> the evidence now supports one narrow CUSTOM MFE result. LigandMPNN–ESMFold produced a useful exploratory timing pair but failed its approval audit; Evo2’s independent audit routed every proposal back to the parent, demonstrating fail-closed behavior rather than usable coverage.</p></div>
      </section>

      <section className="section-shell split-section">
        <div className="section-heading">
          <div><span className="section-index">02</span><h2>Evidence cohorts</h2></div>
          <p>Development, frozen audit, and paired confirmation stay separate.</p>
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
          <div><span>APPROVAL RULE</span><strong>Freeze the model before external audit; freeze the policy before confirmation</strong></div>
          <p>CUSTOM’s successful result followed this separation. LigandMPNN–ESMFold and Evo2 remain negative results because their independent audits missed the predeclared accuracy or coverage gates.</p>
        </div>
        <div className="training-layout">
          <article className="method-card">
            <div className="card-kicker">CURRENT CONFIRMATION</div>
            <h3>CUSTOM adaptive MFE</h3>
            <p>Four previously unopened seeds produced 4,000 same-pool candidates and four counterbalanced full-versus-adaptive pairs. Every frozen confirmation gate passed.</p>
            <div className="method-flow">
              <span>4 fresh pairs</span><ArrowRight size={15} /><span>4,000 candidates</span><ArrowRight size={15} /><span>4 / 4 exact top ten</span>
            </div>
            <dl>
              <div><dt>Pairing unit</dt><dd>complete candidate pool</dd></div>
              <div><dt>Arm order</dt><dd>counterbalanced</dd></div>
              <div><dt>Net speedup</dt><dd>9.72×</dd></div>
              <div><dt>Experiment status</dt><dd>fresh confirmation pass</dd></div>
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
        <p className="split-warning"><strong>Confirmation is not promotion:</strong> the adaptive bundle remains an experimental result until the scientific-fairness and challenge-cohort review gates are closed. Failed LigandMPNN–ESMFold and Evo2 audits are retained as negative evidence, never reinterpreted as successful fusion.</p>
      </section>

      <section className="section-shell" id="benchmarks">
        <div className="section-heading benchmark-heading">
          <div><span className="section-index">03</span><h2>Full vs fused evidence</h2></div>
          <div className="filter-group" aria-label="Filter benchmark runs">
            {(["all", "confirmed", "paired", "baseline", "missing"] as RunFilter[]).map((filter) => (
              <button key={filter} className={runFilter === filter ? "active" : ""} onClick={() => setRunFilter(filter)}>{filter}</button>
            ))}
          </div>
        </div>
        <div className="paper-warning"><Target size={18} /><div><strong>Keep comparison boundaries explicit.</strong><span>CUSTOM establishes same-pool parity with the pinned released implementation; the LigandMPNN–ESMFold result is objective-matched but rejected; Evo2 is a scaled 4,096-base reproduction with no paired timing result. None of these runs reproduces a wet-lab endpoint.</span></div></div>
        <div className="benchmark-table">
          <div className="benchmark-header"><span>Workload</span><span>Work</span><span>Full</span><span>Fused</span><span>Objective error</span><span /></div>
          {visibleRuns.length === 0 ? <div className="empty-state">No runs match this filter.</div> : visibleRuns.map((run) => (
            <div className="benchmark-block" key={run.id}>
              <button className="benchmark-row" onClick={() => setExpandedRun(expandedRun === run.id ? null : run.id)} aria-expanded={expandedRun === run.id}>
                <span className="workload"><strong>{run.workload}</strong><small>{run.tier}</small></span>
                <span>{run.work}</span>
                <span>{run.fullSeconds === null ? <em className="not-run">not reported</em> : <span className="timing"><Clock3 size={14} /> {formatTime(run.fullSeconds)}</span>}</span>
                <span>{run.fusedSeconds === null ? <em className="not-run">{run.speedup === null ? "not run" : "not reported"}</em> : <span className="timing good"><Gauge size={14} /> {formatTime(run.fusedSeconds)}</span>}</span>
                <span className={run.status === "confirmed" ? "error-good" : run.status === "paired" ? "error-mixed" : "error-missing"}>{run.objectiveError}</span>
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
