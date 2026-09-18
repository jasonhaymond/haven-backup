import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'
import { Button, Card, Code, DocLink, ErrorText, Input } from '../components/ui'
import { HelpBox, Steps } from '../components/HelpBox'
import { DOCS } from '../lib/docs'

const emptyForm = {
  name: '', repo_url: '', ssh_credential_id: '', client_host_id: '',
  passphrase: '', keep_daily: 7, keep_weekly: 4, keep_monthly: 6, keep_yearly: 1,
  expected_interval_hours: 26, notes: '',
}

export default function Repos() {
  const [repos, setRepos] = useState(null)
  const [credentials, setCredentials] = useState([])
  const [hosts, setHosts] = useState([])
  const [form, setForm] = useState(emptyForm)
  const [showForm, setShowForm] = useState(false)
  const [error, setError] = useState(null)
  const [submitting, setSubmitting] = useState(false)

  function load() {
    api.get('/repos').then(setRepos).catch((e) => setError(e.message))
    api.get('/credentials').then(setCredentials)
    api.get('/hosts').then(setHosts)
  }

  useEffect(load, [])

  async function handleSubmit(e) {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await api.post('/repos', {
        ...form,
        ssh_credential_id: Number(form.ssh_credential_id),
        client_host_id: form.client_host_id ? Number(form.client_host_id) : null,
        keep_daily: Number(form.keep_daily),
        keep_weekly: Number(form.keep_weekly),
        keep_monthly: Number(form.keep_monthly),
        keep_yearly: Number(form.keep_yearly),
        expected_interval_hours: Number(form.expected_interval_hours),
      })
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
    if (!confirm('Remove this repository from the portal? (Does not delete the actual Borg repo data.)')) return
    await api.delete(`/repos/${id}`)
    load()
  }

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-xl font-semibold">Repositories</h1>
        <Button onClick={() => setShowForm((v) => !v)}>{showForm ? 'Cancel' : 'Add repository'}</Button>
      </div>

      <HelpBox id="repos" title="Adding a repository">
        <p>
          This portal <strong>monitors and prunes existing Borg repos -- it doesn't create new ones.</strong> Before
          adding one here, initialize it first, from the client host or anywhere that can reach it over SSH:
        </p>
        <Code>borg init --encryption=repokey-blake2 ssh://user@backup-host/./path/to/repo</Code>
        <p>Then, in the form below:</p>
        <Steps>
          <li><strong>Repo URL</strong> -- the exact same URL you just ran <code>borg init</code> against.</li>
          <li>
            <strong>SSH credential</strong> -- the one that reaches the <em>repo/backup host</em> (not necessarily the
            client that creates archives into it) -- add it under <Link to="/credentials" className="underline">SSH Credentials</Link> first
            if you haven't.
          </li>
          <li>
            <strong>Passphrase</strong> -- the exact encryption passphrase from <code>borg init</code>. Get this wrong
            and every operation against this repo will fail with an authentication error.
          </li>
          <li>
            <strong>Created by host</strong> (optional) -- just records which client host creates archives here, for
            the dashboard and the "backup now" button on <Link to="/hosts" className="underline">Client Hosts</Link>.
          </li>
          <li>
            <strong>Retention (keep daily/weekly/monthly/yearly)</strong> -- enforced by this portal via scheduled and
            on-demand <code>borg prune</code>, not by whatever creates the archives. See{' '}
            <DocLink href={`${DOCS}/BORGMATIC_INTEGRATION.md`}>BORGMATIC_INTEGRATION.md</DocLink> for why that split
            matters and how to adjust a client's own borgmatic config to match.
          </li>
        </Steps>
        <p className="mt-2">
          If the credential above reaches a <strong>locked-down/restricted account</strong> on the backup host
          (<code>--restrict-to-path</code>, possibly <code>--append-only</code>), retention here can fail with a
          permission error rather than a bug -- an append-only account can't be pruned by design. See{' '}
          <DocLink href={`${DOCS}/RESTRICTED_SSH_ACCOUNTS.md`}>RESTRICTED_SSH_ACCOUNTS.md</DocLink> before setting a
          retention policy on a repo behind one of those accounts.
        </p>
      </HelpBox>

      {showForm && (
        <Card className="mb-4">
          <form onSubmit={handleSubmit} className="grid grid-cols-2 gap-3">
            <Input label="Name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
            <Input
              label="Repo URL"
              placeholder="ssh://user@backup-host/./path/to/repo"
              value={form.repo_url}
              onChange={(e) => setForm({ ...form, repo_url: e.target.value })}
              className="col-span-2"
              required
            />
            <label className="flex flex-col gap-1 text-sm">
              <span className="font-medium text-slate-700 dark:text-slate-300">SSH credential (reaches the repo host)</span>
              <select
                className="rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-950"
                value={form.ssh_credential_id}
                onChange={(e) => setForm({ ...form, ssh_credential_id: e.target.value })}
                required
              >
                <option value="">Select...</option>
                {credentials.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </label>
            <label className="flex flex-col gap-1 text-sm">
              <span className="font-medium text-slate-700 dark:text-slate-300">Created by host (optional)</span>
              <select
                className="rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-950"
                value={form.client_host_id}
                onChange={(e) => setForm({ ...form, client_host_id: e.target.value })}
              >
                <option value="">None</option>
                {hosts.map((h) => <option key={h.id} value={h.id}>{h.name}</option>)}
              </select>
            </label>
            <Input
              label="Passphrase"
              type="password"
              value={form.passphrase}
              onChange={(e) => setForm({ ...form, passphrase: e.target.value })}
              className="col-span-2"
              required
            />
            <Input label="Keep daily" type="number" value={form.keep_daily} onChange={(e) => setForm({ ...form, keep_daily: e.target.value })} />
            <Input label="Keep weekly" type="number" value={form.keep_weekly} onChange={(e) => setForm({ ...form, keep_weekly: e.target.value })} />
            <Input label="Keep monthly" type="number" value={form.keep_monthly} onChange={(e) => setForm({ ...form, keep_monthly: e.target.value })} />
            <Input label="Keep yearly" type="number" value={form.keep_yearly} onChange={(e) => setForm({ ...form, keep_yearly: e.target.value })} />
            <Input
              label="Expected interval (hours) -- flagged stale if no new archive within this"
              type="number"
              value={form.expected_interval_hours}
              onChange={(e) => setForm({ ...form, expected_interval_hours: e.target.value })}
              className="col-span-2"
            />
            <ErrorText>{error}</ErrorText>
            <div className="col-span-2">
              <Button type="submit" disabled={submitting}>{submitting ? 'Saving...' : 'Save repository'}</Button>
            </div>
          </form>
        </Card>
      )}

      <Card>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-left text-slate-500 dark:border-slate-800 dark:text-slate-400">
              <th className="py-2">Name</th>
              <th>Repo URL</th>
              <th>Retention</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {(repos ?? []).map((r) => (
              <tr key={r.id} className="border-b border-slate-100 last:border-0 dark:border-slate-800">
                <td className="py-2"><Link to={`/repos/${r.id}`} className="font-medium hover:underline">{r.name}</Link></td>
                <td className="max-w-xs truncate text-xs text-slate-500 dark:text-slate-400">{r.repo_url}</td>
                <td className="text-xs text-slate-500 dark:text-slate-400">
                  {r.keep_daily}d / {r.keep_weekly}w / {r.keep_monthly}m / {r.keep_yearly}y
                </td>
                <td className="text-right">
                  <button onClick={() => handleDelete(r.id)} className="text-red-600 hover:underline dark:text-red-400">
                    Remove
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {repos && repos.length === 0 && <p className="py-2 text-sm text-slate-500">No repositories yet.</p>}
      </Card>
    </div>
  )
}
