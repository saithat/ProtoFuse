# Sai workspace

Use this directory for disposable learned-fusion notebooks and experiments. Stable code
belongs under `src/protofuse/sai/`; generated training traces and surrogate weights belong
under ignored `data/analysis/` and `data/models/`.

Do not copy generated Proto collections here. Sai's tools consume Phillip's frozen
collections directly from `proto_programs/` without modifying them.
