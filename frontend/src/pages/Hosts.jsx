import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { Button, Card, ErrorText, Input } from '../components/ui'
import RunStatusModal from '../components/RunStatusModal'

const emptyForm = { name: '', ssh_credential_id: '', borgmatic_config_path: '/etc/borgmatic/config.yaml', notes: '' }

export default function Hosts() {
  const [hosts, setHosts] = useState(null)
  const [credentials, setCredentials] = useState([])
  const [repos, setRepos] = useState([])
  const [form, setForm] = useState(emptyForm)
  const [showForm, setShowForm] = useState(false)
  const [error, setError] = useState(null)
  const [submitting, setSubmitting] = useState(false)
  const [activeRun, setActiveRun] = useState(null) // { runId }
  const [repoChoice, setRepoChoice] = useState({}) // hostId -> repoId

  function load() {
    api.get('/hosts').then(setHosts).catch((e) => setError(e.message))
    api.get('/credentials').then(setCredentials)
    api.get('/repos').then(setRepos)
  }

  useEffect(load, [])

  async function handleSubmit(e) {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await api.post('/hosts', { ...form, ssh_credential_id: Number(form.ssh_credential_id) })
      setForm(emptyForm)
      setShowForm(false)
      load()
    } catch (err) {
      setError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  async function handleDelete(id) {
    if (!confirm('Delete this host?')) return
    await api.delete(`/hosts/${id}`)
    load()
  }

  async function handleBackupNow(hostId) {
    const repoId = repoChoice[hostId]
    if (!repoId) {
      alert('Choose which repository this backup targets first.')
      return
    }
    const run = await api.post(`/hosts/${hostId}/backup-now?repo_id=${repoId}`)
    setActiveRun(run.id)
  }

  const reposForHost = (hostId) => repos.filter((r) => r.client_host_id === hostId || repos.length > 0)

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-xl font-semibold">Client Hosts</h1>
        <Button onClick={() => setShowForm((v) => !v)}>{showForm ? 'Cancel' : 'Add host'}</Button>
      </div>

      {showForm && (
        <Card className="mb-4">
          <form onSubmit={handleSubmit} className="grid grid-cols-2 gap-3">
            <Input label="Name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
            <label className="flex flex-col gap-1 text-sm">
              <span className="font-medium text-slate-700 dark:text-slate-300">SSH credential</span>
              <select
                className="rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-950"
                value={form.ssh_credential_id}
                onChange={(e) => setForm({ ...form, ssh_credential_id: e.target.value })}
                required
              >
                <option value="">Select...</option>
                {credentials.map((c) => (
                  <option key={c.id} value={c.id}>{c.name} ({c.hostname})</option>
                ))}
              </select>
            </label>
            <Input
              label="borgmatic config path"
              value={form.borgmatic_config_path}
              onChange={(e) => setForm({ ...form, borgmatic_config_path: e.target.value })}
              className="col-span-2"
              required
            />
            <Input label="Notes" value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} className="col-span-2" />
            <ErrorText>{error}</ErrorText>
            <div className="col-span-2">
              <Button type="submit" disabled={submitting}>{submitting ? 'Saving...' : 'Save host'}</Button>
            </div>
          </form>
        </Card>
      )}

      <Card>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-left text-slate-500 dark:border-slate-800 dark:text-slate-400">
              <th className="py-2">Name</th>
              <th>borgmatic config</th>
              <th>Backup now, into</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {(hosts ?? []).map((h) => (
              <tr key={h.id} className="border-b border-slate-100 last:border-0 dark:border-slate-800">
                <td className="py-2">{h.name}</td>
                <td className="text-xs text-slate-500 dark:text-slate-400">{h.borgmatic_config_path}</td>
                <td>
                  <div className="flex items-center gap-2">
                    <select
                      className="rounded-md border border-slate-300 bg-white px-2 py-1 text-xs dark:border-slate-700 dark:bg-slate-950"
                      value={repoChoice[h.id] ?? ''}
                      onChange={(e) => setRepoChoice({ ...repoChoice, [h.id]: Number(e.target.value) })}
                    >
                      <option value="">Choose repo...</option>
                      {reposForHost(h.id).map((r) => (
                        <option key={r.id} value={r.id}>{r.name}</option>
                      ))}
                    </select>
                    <Button variant="secondary" onClick={() => handleBackupNow(h.id)}>Backup now</Button>
                  </div>
                </td>
                <td className="text-right">
                  <button onClick={() => handleDelete(h.id)} className="text-red-600 hover:underline dark:text-red-400">
                    Delete
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {hosts && hosts.length === 0 && <p className="py-2 text-sm text-slate-500">No client hosts yet.</p>}
      </Card>

      <RunStatusModal kind="backup" runId={activeRun} title="Backup run" onClose={() => setActiveRun(null)} />
    </div>
  )
}
