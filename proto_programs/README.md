# Phillip-to-Sai program corpus

Phillip writes reviewed collections to `generated/<collection_id>/`; Sai reads those
frozen folders to discover and train reusable fusions. This is the only artifact handoff.

Each collection contains `collection.json` and readable Python files with a synchronous
`build_program()` entry point. `src/protofuse/program_collection.py` validates metadata,
paths, review status, and hashes without executing the files.

Names such as `design_001.py` and `design_002.py` are stable manifest ordinals, not
semantic labels. Most reviewed two-file collections currently use `001` for the full tier
and `002` for the reduced smoke tier, but multi-program collections may contain several
full variants. Read the module docstring and `build_program()` tier selection. Use “full,”
not “real”: a smoke program is also executable and reviewed, just intentionally smaller.

A folder may exist here with `reviewed=false` while its paper encoding awaits human
review. Such a folder is generated output, not an active Phillip-to-Sai handoff; the
controlled analyzer rejects it by default.

Do not store paper text, confidential inputs, credentials, run outputs, teacher traces,
calibration data, or model weights here.
