# Contributed lane

Owner-provided workflows and papers for Sai to rank, analyze, and optimize.

Each scenario directory needs:

- `manifest.json` with `source_lane: "contributed"` and contributor attribution
- `methodology.json` — a redistributable `MethodologySpec`
- a matching entry in `philip-sai-integrations/v1/catalog.json`

Sai consumes these the same way as his own lane; the lane label preserves provenance.
