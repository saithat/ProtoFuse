# Phillip-to-Sai program corpus

Phillip writes reviewed collections to `generated/<collection_id>/`; Sai reads those
frozen folders to discover and train reusable fusions. This is the only artifact handoff.

Each collection contains `collection.json` and readable Python files with a synchronous
`build_program()` entry point. `src/protofuse/program_collection.py` validates metadata,
paths, review status, and hashes without executing the files.

Do not store paper text, confidential inputs, credentials, run outputs, teacher traces,
calibration data, or model weights here.
