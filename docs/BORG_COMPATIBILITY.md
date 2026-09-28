# Borg/borgmatic version compatibility -- please verify against your setup

[← Back to README](../README.md) · [Architecture](ARCHITECTURE.md) ·
[Deployment](DEPLOYMENT.md) ·
[Borgmatic integration](BORGMATIC_INTEGRATION.md) ·
[Restricted SSH accounts](RESTRICTED_SSH_ACCOUNTS.md) ·
[Security](SECURITY.md) · [Backup](BACKUP.md) ·
[Client enrollment](CLIENT_ENROLLMENT.md)

## Contents
- [Verifying against your Borg version](#verifying)
- [Borg 1.x vs 2.x](#borg-1x-vs-2x)

This portal's parsing of `borg`'s output (`backend/app/borg_runner.py`) was
first written against Borg's documented JSON schemas without a live repo to
test on. **As of v1.0.0 it has been exercised against real repositories**:
the portal container's borg 1.4.0 running `info`, `list`, `prune` (dry run
and real) and `check` against repos created by borg 1.2.4 (Debian 12) and
1.2.8 (Ubuntu 24.04) clients, over SSH to a borg 1.2.4 backup server with
`--restrict-to-path`/`--restrict-to-repository` accounts. That test found
one real bug, fixed in 1.0.0: Borg 1.x's `info --json` has no
`repository.archive_count`, and the parser used to fall back to
`cache.stats.total_chunks`, so the dashboard showed the chunk count as the
number of archives. The count now comes from `borg list`.

Other Borg versions (in particular 2.x, and whatever your backup server
runs) are still worth checking with the commands below.

<a id="verifying"></a>
## Verifying against your Borg version

Before you rely on the parsed numbers in the dashboard, do this once:

```bash
# From wherever the portal container/host can reach your repo:
BORG_PASSPHRASE=... borg info --json ssh://user@backup-host/./repo | head -c 2000
BORG_PASSPHRASE=... borg list --json ssh://user@backup-host/./repo | head -c 2000
BORG_PASSPHRASE=... borg prune --list --stats --dry-run --keep-daily=7 ssh://user@backup-host/./repo
```

**What success looks like:** the `info` command prints a JSON object
containing a top-level `"cache"` key with a nested `"stats"` object (holding
`total_size`, `total_csize`, etc.) and a top-level `"repository"` key. Borg
1.x has no `"archive_count"` there; the portal counts archives from `list`
instead. The `list` command prints a JSON object with an
`"archives"` array, each entry having `"name"` and `"time"` fields. The
`prune --dry-run` command prints one `Would prune: <archive name>` line per
archive it would remove (zero lines is fine if none would be). If all three
match, the portal's parsing will work as-is -- skip straight to using it.
If any of them look different, keep reading below for exactly which fields
to adjust and where.

Compare the shape against what `parse_info` / `parse_list` / `parse_prune` in
`backend/app/borg_runner.py` expect:

- `parse_info` reads `data["cache"]["stats"]["total_size" / "total_csize" /
  "unique_csize" / "unique_size"]`, and `data["repository"]["archive_count"]`
  only if present (it isn't in Borg 1.x -- the archive count then comes from
  `parse_list`).
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

<a id="borg-1x-vs-2x"></a>
## Borg 1.x vs 2.x

This was written with Borg 1.2.x's CLI/output shapes in mind. Borg 2.x
changed several things (repository format, some command syntax). If you're on
Borg 2.x, expect to need adjustments in `borg_runner.py`'s command builders
and parsers.
