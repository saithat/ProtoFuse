# Phillip-to-Sai handoff

Phillip writes reviewed program collections to `generated/<collection_id>/`. Sai reads
those frozen folders when building learned fusion.

Each collection contains `collection.json` plus readable Python files that expose
`build_program()` and are inert on import. Do not store paper text, confidential inputs,
credentials, run outputs, teacher traces, or model weights here.
