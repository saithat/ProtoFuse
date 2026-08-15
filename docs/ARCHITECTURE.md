# Architecture

## Single-package integration flow

```text
Paper / Paperclip
       |
       v
shared scientific_agent
       |
       v
MethodologySpec v1.0
       |
       v
Phillip: reviewed paper-to-Proto generation
       |
       v
proto_programs/generated/<collection_id>/*.py
       |
       v
Sai: catalog and profile recurring model-step groups
       |
       v
select one expensive fusion candidate
       |
       v
multi-output surrogate + calibrated deferral gate
       |                            |
       | confident and in-domain    | uncertain / OOD / final validation
       v                            v
surrogate outputs             original full model steps
       |                            |
       +-------------+--------------+
                     v
              optimizer decision
```

Everything lives in the ProtoFuse package. Proto Language remains a pinned dependency;
Sai does not need a separate fork unless a later experiment proves that required
instrumentation cannot be implemented through wrapping and the public runtime objects.

## Integration contracts

`MethodologySpec` is the scientific seam. Phillip's generator consumes the specification
through a reviewed component registry and writes a directory of readable Proto Python
programs. Each file exposes `build_program()` and does nothing expensive on import.

The directory contract is defined in `docs/PROGRAM_COLLECTION.md`. Phillip's only handoff
action is generating and reviewing that collection. A collection-level manifest is
written automatically so Sai can verify hashes, Proto version, registry version, input
roles, and safety approval before loading any program.

Sai's analyzer imports the reviewed builders, inspects and profiles their Program stages,
generators, constraints, and model/tool calls, and canonicalizes recurring step groups.
The word "graph" is descriptive rather than a claim that Proto has a tensor execution
graph like PyTorch or TensorFlow.

## Learned fusion contract

Learned fusion approximates several recurring full-model steps with one multi-output
surrogate. It is always paired with an abstention gate. The surrogate may act only when
the input is within its applicability domain and its calibrated uncertainty supports the
downstream decision. Otherwise the original full-model steps run.

The router defers when an input is out of domain, ensemble disagreement is high,
prediction intervals cross a scientific threshold or top-k boundary, a required output
is unsupported, or a rare-failure rule requests full evaluation. Final selected
candidates receive full-model validation unless an explicit joint decision changes that
policy.

## Execution safety

Paper text is untrusted. Generated programs may instantiate only reviewed registry
symbols with typed parameters; they must never copy paper-provided code, imports, shell
commands, URLs, or unreviewed model identifiers. Raw teacher traces, confidential inputs,
surrogate weights, and model caches remain under ignored `data/` paths.
