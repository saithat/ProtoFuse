# ppi-interface-specificity

Frozen Phillip handoff collection for region-local PPI interface specificity MCMC.

Each `build_program()` is one region-pass step inside `run_ppi_interface_specificity(tier="full")`
(100 MCMC steps × 2 interface patches). Smoke tier (`design_002.py`) uses 20 steps and ESM-2
proposals on interface patch 1 only.

Methodology fixture: `workspaces/phillip/fixtures/ppi-interface-specificity/methodology.json`.
