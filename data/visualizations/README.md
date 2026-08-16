# Curated visualization data

This directory is intentionally tracked. It contains the small, reviewed artifacts needed to
render final research outputs without committing raw runs, teacher traces, calibration rows,
credentials, model weights, or caches.

Regenerate the bundle from local ignored result data:

```bash
python3 scripts/build_visualization_bundle.py --strict
python3 scripts/build_evaluation_report.py --strict
```

`manifest.json` is the entry point. Each candidate records:

- a stable candidate, fixture, tier, arm, segment, and artifact-role identity;
- the final or explicitly partial sequence, alphabet, length, hash, and FASTA path;
- a versioned objective vector with direction and units when available;
- related structure and molecule identifiers;
- the source artifact path and hash.

Structures record their role (`final`, `intermediate`, or reference), file format, path, hash,
chain IDs, and atom counts. Molecule records are reserved for canonical SMILES, an optional
molblock/SDF path, 2D coordinates, role, and provenance. The currently empty `molecules` array
is deliberate: no final small-molecule artifact has been produced yet.

The bundle may contain research sequences and generated structures. Review additions before
publication. Raw inputs stay under the ignored `data/analysis/` and `data/runs/` directories;
only this curated export belongs in Git.
