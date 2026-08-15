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

## Execution safety gate

Paper text is untrusted. Extracted component names never become Python imports or shell
commands. `compile_proto_plan` accepts a separately reviewed name-to-Proto-symbol
registry. A plan is marked executable only after every component is bound. The next
implementation milestone is a registry-backed builder that instantiates those approved
symbols using typed, validated parameter mappings.
