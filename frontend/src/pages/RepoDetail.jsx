import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { api } from '../lib/api'
import { formatBytes, formatDateTime, formatRelativeTime } from '../lib/format'
import { Badge, Button, Card, ErrorText } from '../components/ui'
import RunStatusModal from '../components/RunStatusModal'

function statusFor(snapshot) {
  if (!snapshot) return { tone: 'neutral', label: 'Never checked' }
  if (!snapshot.ok) return { tone: 'danger', label: 'Error' }
  if (snapshot.is_stale) return { tone: 'warning', label: 'Stale' }
  return { tone: 'success', label: 'Healthy' }
}

export default function RepoDetail() {
  const { repoId } = useParams()
  const [repo, setRepo] = useState(null)
  const [status, setStatus] = useState(null)
  const [backupRuns, setBackupRuns] = useState([])
  const [pruneRuns, setPruneRuns] = useState([])
  const [error, setError] = useState(null)
  const [refreshing, setRefreshing] = useState(false)
  const [activeRun, setActiveRun] = useState(null) // { kind, id }

  function load() {
    api.get('/repos').then((repos) => setRepo(repos.find((r) => String(r.id) === repoId)))
    api.get(`/repos/${repoId}/status`).then(setStatus).catch((e) => setError(e.message))
    api.get(`/runs/backups?repo_id=${repoId}&limit=10`).then(setBackupRuns)
    api.get(`/runs/prunes?repo_id=${repoId}&limit=10`).then(setPruneRuns)
  }

  useEffect(load, [repoId])

  async function handleRefresh() {
    setRefreshing(true)
    try {
      setStatus(await api.post(`/repos/${repoId}/refresh`))
    } catch (err) {
      setError(err.message)
    } finally {
      setRefreshing(false)
    }
  }

  async function handlePrune(dryRun) {
    const run = await api.post(`/repos/${repoId}/prune?dry_run=${dryRun}`)
    setActiveRun({ kind: 'prune', id: run.id })
  }

  async function handleCheck() {
    const run = await api.post(`/repos/${repoId}/check`)
    setActiveRun({ kind: 'check', id: run.id })
  }

  function closeModalAndReload() {
    setActiveRun(null)
    load()
  }

  if (!repo) return <p className="text-sm text-slate-500">Loading...</p>
  const s = statusFor(status)

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">{repo.name}</h1>
          <p className="text-xs text-slate-500 dark:text-slate-400">{repo.repo_url}</p>
        </div>
        <Badge tone={s.tone}>{s.label}</Badge>
      </div>

      <ErrorText>{error}</ErrorText>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="font-semibold">Status</h2>
            <Button variant="secondary" onClick={handleRefresh} disabled={refreshing}>
              {refreshing ? 'Refreshing...' : 'Refresh now'}
            </Button>
          </div>
          <dl className="grid grid-cols-2 gap-y-2 text-sm">
            <dt className="text-slate-500 dark:text-slate-400">Last archive</dt>
            <dd>{status?.last_archive_name ?? '—'} ({formatRelativeTime(status?.last_archive_time)})</dd>
            <dt className="text-slate-500 dark:text-slate-400">Archives</dt>
            <dd>{status?.num_archives ?? '—'}</dd>
            <dt className="text-slate-500 dark:text-slate-400">Original size</dt>
            <dd>{formatBytes(status?.original_size)}</dd>
            <dt className="text-slate-500 dark:text-slate-400">Compressed size</dt>
            <dd>{formatBytes(status?.compressed_size)}</dd>
            <dt className="text-slate-500 dark:text-slate-400">Deduplicated size</dt>
            <dd>{formatBytes(status?.deduplicated_size)}</dd>
            <dt className="text-slate-500 dark:text-slate-400">Checked</dt>
            <dd>{formatRelativeTime(status?.captured_at)}</dd>
          </dl>
          {status?.error && <p className="mt-3 text-sm text-red-600 dark:text-red-400">{status.error}</p>}
        </Card>

        <Card>
          <h2 className="mb-3 font-semibold">Retention policy</h2>
          <dl className="grid grid-cols-2 gap-y-1 text-sm">
            <dt className="text-slate-500 dark:text-slate-400">Daily</dt><dd>{repo.keep_daily}</dd>
            <dt className="text-slate-500 dark:text-slate-400">Weekly</dt><dd>{repo.keep_weekly}</dd>
            <dt className="text-slate-500 dark:text-slate-400">Monthly</dt><dd>{repo.keep_monthly}</dd>
            <dt className="text-slate-500 dark:text-slate-400">Yearly</dt><dd>{repo.keep_yearly}</dd>
          </dl>
          <div className="mt-4 flex flex-col gap-2">
            <Button variant="secondary" onClick={() => handlePrune(true)}>Preview prune (dry run)</Button>
            <Button variant="danger" onClick={() => handlePrune(false)}>Apply retention now</Button>
            <Button variant="secondary" onClick={handleCheck}>Run integrity check</Button>
          </div>
        </Card>
      </div>

      <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <h2 className="mb-3 font-semibold">Recent backup runs</h2>
          <RunTable runs={backupRuns} onOpen={(id) => setActiveRun({ kind: 'backup', id })} extra={(r) => r.triggered_by} />
        </Card>
        <Card>
          <h2 className="mb-3 font-semibold">Recent prune runs</h2>
          <RunTable
            runs={pruneRuns}
            onOpen={(id) => setActiveRun({ kind: 'prune', id })}
            extra={(r) => `${r.dry_run ? 'dry run' : 'applied'} · ${r.archives_deleted} deleted`}
          />
        </Card>
      </div>

      <RunStatusModal
        kind={activeRun?.kind}
        runId={activeRun?.id}
        title={activeRun ? `${activeRun.kind} run` : ''}
        onClose={closeModalAndReload}
      />
    </div>
  )
}

function RunTable({ runs, onOpen, extra }) {
  const tone = { running: 'warning', success: 'success', failed: 'danger' }
  if (runs.length === 0) return <p className="text-sm text-slate-500">No runs yet.</p>
  return (
    <table className="w-full text-sm">
      <tbody>
        {runs.map((r) => (
          <tr key={r.id} className="border-b border-slate-100 last:border-0 dark:border-slate-800">
            <td className="py-1.5"><Badge tone={tone[r.status]}>{r.status}</Badge></td>
            <td className="text-xs text-slate-500 dark:text-slate-400">{formatDateTime(r.started_at)}</td>
            <td className="text-xs text-slate-500 dark:text-slate-400">{extra(r)}</td>
            <td className="text-right">
              <button onClick={() => onOpen(r.id)} className="text-xs underline">View log</button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
