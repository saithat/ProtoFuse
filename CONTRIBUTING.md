# Contributing directly to main

This two-person hackathon repository intentionally uses trunk-based development.

1. Work in the directory assigned in `docs/TEAM.md`. Treat generated Proto collections
   as a frozen interface between Phillip and Sai.
2. Keep commits small and single-purpose.
3. Before editing a shared contract, message the other person and agree on the field
   change.
4. Before pushing, run `git pull --rebase origin main`, resolve any conflict locally,
   then run the checks below.
5. Push directly to `main`. Never force-push `main`.

```bash
uv run ruff check .
uv run pytest
```

Generated paper content and experiment outputs belong under ignored `data/` paths.
Commit a small, synthetic example only when it is needed for a test.

Raw teacher traces, surrogate weights, and calibration datasets belong under ignored
`data/` paths. Commit only compact synthetic fixtures and reviewed evaluation reports.
