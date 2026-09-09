# Borg/borgmatic version compatibility -- please verify against your setup

This portal's parsing of `borg`'s output (`backend/app/borg_runner.py`) was
written against Borg's documented JSON schemas and typical text output, but
**it was not tested against a live Borg repository** while building it (the
sandbox this was developed in couldn't build Borg's native extensions and had
no network access to a real Borg server). Before you rely on the parsed
numbers in the dashboard, do this once:

```bash
# From wherever the portal container/host can reach your repo:
BORG_PASSPHRASE=... borg info --json ssh://user@backup-host/./repo | head -c 2000
BORG_PASSPHRASE=... borg list --json ssh://user@backup-host/./repo | head -c 2000
BORG_PASSPHRASE=... borg prune --list --stats --dry-run --keep-daily=7 ssh://user@backup-host/./repo
```

Compare the shape against what `parse_info` / `parse_list` / `parse_prune` in
`backend/app/borg_runner.py` expect:

- `parse_info` reads `data["cache"]["stats"]["total_size" / "total_csize" /
  "unique_csize" / "unique_size"]` and `data["repository"]["archive_count"]`.
  Borg 1.2's `borg info --json` has this `cache.stats` block; if your version
  differs, the numbers on the dashboard will just come back as `null` --
  nothing crashes, but sizes won't render. The full raw JSON isn't currently
  persisted for `info` (only parsed fields, since it's polled frequently) --
  if you need to debug a mismatch, run the command above by hand.
- `parse_list` reads `data["archives"][*]["name"]` and `["time"]` (falls back
  to `["start"]`). This shape has been stable across Borg 1.x.
- `parse_prune` counts lines starting with `Would prune:` (dry run) or
  `Pruning archive` (real run) in the combined stdout+stderr. If your Borg
  version phrases these differently, the count will read as `0` even on a
  successful prune -- **the prune itself still happens correctly** (that's a
  real `borg prune` invocation), only the "N archives deleted" number in the
  UI would be off. The full raw output is always stored on the `PruneRun`
  record (`output_log`), so you can always read what actually happened there
  regardless of whether the count parsed correctly.

If something doesn't match, the fix is narrowly scoped to
`backend/app/borg_runner.py`'s `parse_info`/`parse_list`/`parse_prune`
functions -- update the key paths/regex there, covered by
`backend/tests/test_borg_runner.py`'s fixtures (update those fixtures to match
your version's real output while you're at it).

## Borg 1.x vs 2.x

This was written with Borg 1.2.x's CLI/output shapes in mind. Borg 2.x
changed several things (repository format, some command syntax). If you're on
Borg 2.x, expect to need adjustments in `borg_runner.py`'s command builders
and parsers.
