import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'
import { formatBytes, formatRelativeTime } from '../lib/format'
import { Badge, Card, ErrorText } from '../components/ui'

function statusFor(entry) {
  if (entry.ok === null) return { tone: 'neutral', label: 'Never checked' }
  if (!entry.ok) return { tone: 'danger', label: 'Error' }
  if (entry.is_stale) return { tone: 'warning', label: 'Stale' }
  return { tone: 'success', label: 'Healthy' }
}

export default function Dashboard() {
  const [entries, setEntries] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    api.get('/dashboard').then(setEntries).catch((e) => setError(e.message))
  }, [])

  if (error) return <ErrorText>{error}</ErrorText>
  if (!entries) return <p className="text-sm text-slate-500">Loading...</p>

  if (entries.length === 0) {
    return (
      <Card>
        <p className="text-sm text-slate-500">
          No repositories configured yet. Add an SSH credential, then a repository, under{' '}
          <Link to="/repos" className="underline">Repositories</Link>.
        </p>
      </Card>
    )
  }

  return (
    <div>
      <h1 className="mb-4 text-xl font-semibold">Dashboard</h1>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {entries.map((entry) => {
          const status = statusFor(entry)
          return (
            <Link key={entry.repo_id} to={`/repos/${entry.repo_id}`}>
              <Card className="h-full transition-shadow hover:shadow-md">
                <div className="mb-2 flex items-start justify-between">
                  <div>
                    <div className="font-semibold">{entry.repo_name}</div>
                    {entry.client_host_name && (
                      <div className="text-xs text-slate-500 dark:text-slate-400">{entry.client_host_name}</div>
                    )}
                  </div>
                  <Badge tone={status.tone}>{status.label}</Badge>
                </div>
                <dl className="mt-3 grid grid-cols-2 gap-y-1 text-sm">
                  <dt className="text-slate-500 dark:text-slate-400">Last archive</dt>
                  <dd className="text-right">{formatRelativeTime(entry.last_archive_time)}</dd>
                  <dt className="text-slate-500 dark:text-slate-400">Archives</dt>
                  <dd className="text-right">{entry.num_archives ?? '—'}</dd>
                  <dt className="text-slate-500 dark:text-slate-400">Deduplicated size</dt>
                  <dd className="text-right">{formatBytes(entry.deduplicated_size)}</dd>
                </dl>
                {entry.error && <p className="mt-2 truncate text-xs text-red-600 dark:text-red-400" title={entry.error}>{entry.error}</p>}
              </Card>
            </Link>
          )
        })}
      </div>
    </div>
  )
}
