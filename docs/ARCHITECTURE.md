# Architecture

## Integration flow

```text
Paper / Paperclip
       |
       v
shared scientific_agent  -- both improve prompts, evidence, and evaluation
       |
       v
MethodologySpec v1.0     -- stable integration contract
       |
       +--------------------------+
       |                          |
       v                          v
Phillip: end-to-end pipeline      Sai: common topology ranking/optimization
       |                          |
       |-- graph + profile ------>|
       |<-- prepared state + gate-|
       +------------+-------------+
                    v
               ProtoPlan
                    |
          explicit binding review
                    v
         executable Proto workflow
```

## Why the contract is the seam

`MethodologySpec` contains exactly the method fields the project needs: generators,
constraints and scores, optimizers, model dependencies, parameters, workflow topology,
selection thresholds, experimental measurements, evidence, assumptions, and unknowns.

The scientific agent produces this contract. Sai's code consumes it without knowing
which model performed extraction. Phillip's pipeline consumes Sai's ranked
`TopologyRecommendation` without depending on the ranking implementation.

After component binding, Phillip also emits the normalized computation-graph and reuse
workload handoff defined in `docs/GRAPH_HANDOFF.md`. Sai uses its stable typed graph,
input roles, and aggregate profile to identify amortizable work. The first optimization
target is ProtoStage: split fixed context from varying candidate work, cache typed
prepared state, and retain a residual graph with equivalent semantics where possible.
Sai returns a prepared-module plan, reviewable graph patch, and benchmark gate. Joint
decisions occur at methodology approval, graph/workload freeze, reuse-mode selection,
prepared-state approval, benchmark acceptance, and final integration.

## Execution safety gate

Paper text is untrusted. Extracted component names never become Python imports or shell
commands. `compile_proto_plan` accepts a separately reviewed name-to-Proto-symbol
registry. A plan is marked executable only after every component is bound. The next
implementation milestone is a registry-backed builder that instantiates those approved
symbols using typed, validated parameter mappings.
