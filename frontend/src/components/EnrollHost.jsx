import { useState } from 'react'
import { api } from '../lib/api'
import { Badge, Button, Card, Code, DocLink, ErrorText, Input, Textarea } from './ui'
import { DOCS } from '../lib/docs'

const emptyForm = {
  name: '',
  address: '',
  ssh_port: 22,
  backup_credential_id: '',
  repo_base_path: '/srv/backups/haven-backup',
  source_directories: '/etc\n/root\n/home',
  schedule: '*-*-* 02:00:00',
  keep_daily: 7,
  keep_weekly: 4,
  keep_monthly: 6,
  keep_yearly: 1,
  expected_interval_hours: 26,
}

const selectClass =
  'rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-950'

function CopyButton({ text }) {
  const [copied, setCopied] = useState(false)
  async function copy() {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      // Clipboard API needs a secure context -- over plain http the user selects the text by hand.
    }
  }
  return (
    <Button variant="secondary" type="button" onClick={copy}>
      {copied ? 'Copied' : 'Copy'}
    </Button>
  )
}

function installCommands(portal, token, allowHttp) {
  const flags = `--portal ${portal} --token ${token}${allowHttp ? ' --allow-http' : ''}`
  return {
    oneLine: `curl -fsSL ${portal}/api/enroll/install.sh | sudo bash -s -- ${flags}`,
    inspectFirst:
      `curl -fsSLo haven-enroll.sh ${portal}/api/enroll/install.sh\n` +
      `less haven-enroll.sh\n` +
      `sudo bash haven-enroll.sh ${flags}`,
  }
}

export function EnrollForm({ credentials, onCreated, onCancel }) {
  const [form, setForm] = useState(emptyForm)
  const [portal, setPortal] = useState(window.location.origin)
  const [allowHttp, setAllowHttp] = useState(false)
  const [error, setError] = useState(null)
  const [submitting, setSubmitting] = useState(false)
  const [created, setCreated] = useState(null)

  const set = (field) => (e) => setForm({ ...form, [field]: e.target.value })
  const isHttp = portal.startsWith('http://')

  async function handleSubmit(e) {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      const body = {
        ...form,
        backup_credential_id: Number(form.backup_credential_id),
        source_directories: form.source_directories.split('\n'),
      }
      for (const n of ['ssh_port', 'keep_daily', 'keep_weekly', 'keep_monthly', 'keep_yearly', 'expected_interval_hours']) {
        body[n] = Number(body[n])
      }
      const result = await api.post('/enrollments', body)
      setCreated(result)
      onCreated()
    } catch (err) {
      setError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  if (created) {
    const portalUrl = portal.replace(/\/+$/, '')
    const cmds = installCommands(portalUrl, created.token, isHttp && allowHttp)
    return (
      <Card className="mb-4 space-y-3">
        <h2 className="font-semibold">Run this on {created.name}, as a user that can sudo</h2>
        <div className="flex flex-col gap-2 sm:flex-row sm:items-start">
          <div className="min-w-0 flex-1"><Code wrap>{cmds.oneLine}</Code></div>
          <CopyButton text={cmds.oneLine} />
        </div>
        <p className="text-sm text-slate-600 dark:text-slate-400">
          Prefer to read it before running it as root? Same result:
        </p>
        <div className="flex flex-col gap-2 sm:flex-row sm:items-start">
          <div className="min-w-0 flex-1"><Code wrap>{cmds.inspectFirst}</Code></div>
          <CopyButton text={cmds.inspectFirst} />
        </div>
        <p className="text-sm">
          <strong>This command is shown only once</strong> and works once, until{' '}
          {new Date(created.expires_at).toLocaleString()}. If you lose it, revoke this enrollment and create a new
          one. It will print one line to paste on the backup server ({created.backup_server_account}), which also
          appears in the enrollments list below once the host has registered.
        </p>
        <Button onClick={onCancel}>Done</Button>
      </Card>
    )
  }

  return (
    <Card className="mb-4">
      <form onSubmit={handleSubmit} className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Input label="Name (host and repo)" value={form.name} onChange={set('name')} placeholder="pve1" required />
        <Input
          label="Address the portal reaches it at"
          value={form.address}
          onChange={set('address')}
          placeholder="10.0.0.5 or pve1.lan"
          required
        />
        <label className="flex flex-col gap-1 text-sm">
          <span className="font-medium text-slate-700 dark:text-slate-300">Backup server (SSH credential)</span>
          <select className={selectClass} value={form.backup_credential_id} onChange={set('backup_credential_id')} required>
            <option value="">Select...</option>
            {credentials.map((c) => (
              <option key={c.id} value={c.id}>{c.name} ({c.username}@{c.hostname})</option>
            ))}
          </select>
        </label>
        <Input label="Repo folder on the backup server" value={form.repo_base_path} onChange={set('repo_base_path')} required />
        <Textarea
          label="Folders to back up (one per line)"
          rows={4}
          value={form.source_directories}
          onChange={set('source_directories')}
          required
        />
        <div className="flex flex-col gap-3">
          <Input label="Schedule (systemd OnCalendar)" value={form.schedule} onChange={set('schedule')} required />
          <Input label="SSH port on the client" type="number" value={form.ssh_port} onChange={set('ssh_port')} required />
        </div>
        <div className="grid grid-cols-2 gap-3 sm:col-span-2 sm:grid-cols-5">
          <Input label="Keep daily" type="number" min="0" value={form.keep_daily} onChange={set('keep_daily')} />
          <Input label="Keep weekly" type="number" min="0" value={form.keep_weekly} onChange={set('keep_weekly')} />
          <Input label="Keep monthly" type="number" min="0" value={form.keep_monthly} onChange={set('keep_monthly')} />
          <Input label="Keep yearly" type="number" min="0" value={form.keep_yearly} onChange={set('keep_yearly')} />
          <Input label="Stale after (h)" type="number" min="1" value={form.expected_interval_hours} onChange={set('expected_interval_hours')} />
        </div>
        <div className="sm:col-span-2">
          <Input label="Portal URL the client will use" value={portal} onChange={(e) => setPortal(e.target.value)} required />
        </div>
        {isHttp && (
          <div className="rounded-md sm:col-span-2 border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-200">
            <p>
              This portal URL is plain <code>http://</code> -- the one-time token and the new repo's passphrase would
              cross the network unencrypted, so the install script refuses it by default. Use the portal's
              https address if it has one.
            </p>
            <label className="mt-2 flex items-center gap-2">
              <input type="checkbox" checked={allowHttp} onChange={(e) => setAllowHttp(e.target.checked)} />
              Allow plain http anyway (trusted LAN only -- adds <code>--allow-http</code>)
            </label>
          </div>
        )}
        <ErrorText>{error}</ErrorText>
        <div className="flex gap-2 sm:col-span-2">
          <Button type="submit" disabled={submitting}>{submitting ? 'Generating...' : 'Generate install command'}</Button>
          <Button type="button" variant="secondary" onClick={onCancel}>Cancel</Button>
        </div>
      </form>
    </Card>
  )
}

const statusTone = { pending: 'warning', claimed: 'success', expired: 'neutral' }

export function EnrollmentList({ enrollments, onChange }) {
  if (!enrollments || enrollments.length === 0) return null

  async function handleDelete(e) {
    const msg =
      e.status === 'claimed'
        ? 'Remove this enrollment record? The host and repo it created stay -- delete those from their own pages.'
        : 'Revoke this install command? It will stop working immediately.'
    if (!confirm(msg)) return
    await api.delete(`/enrollments/${e.id}`)
    onChange()
  }

  return (
    <Card className="mb-4">
      <h2 className="mb-2 font-semibold">Enrollments</h2>
      <div className="space-y-3">
        {enrollments.map((e) => (
          <div key={e.id} className="border-b border-slate-100 pb-3 text-sm last:border-0 last:pb-0 dark:border-slate-800">
            <div className="flex items-start justify-between gap-2">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium">{e.name}</span>
                <Badge tone={statusTone[e.status]}>{e.status}</Badge>
                <span className="text-xs text-slate-500 dark:text-slate-400">
                  {e.status === 'claimed'
                    ? `registered from ${e.claimed_hostname} ${new Date(e.claimed_at).toLocaleString()}`
                    : e.status === 'pending'
                      ? `expires ${new Date(e.expires_at).toLocaleString()}`
                      : 'expired unused'}
                </span>
              </div>
              <button onClick={() => handleDelete(e)} className="text-red-600 hover:underline dark:text-red-400">
                {e.status === 'claimed' ? 'Remove' : 'Revoke'}
              </button>
            </div>
            {e.backup_server_line && (
              <div className="mt-2 space-y-1">
                <p className="text-slate-600 dark:text-slate-400">
                  On the backup server, append this line to{' '}
                  <code>~{e.backup_server_account.split('@')[0]}/.ssh/authorized_keys</code> (if you haven't already --
                  the install script waits for it):
                </p>
                <div className="flex flex-col gap-2 sm:flex-row sm:items-start">
                  <div className="min-w-0 flex-1"><Code wrap>{e.backup_server_line}</Code></div>
                  <CopyButton text={e.backup_server_line} />
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
      <p className="mt-3 text-xs text-slate-500 dark:text-slate-400">
        Full walkthrough, including the manual equivalent of every step:{' '}
        <DocLink href={`${DOCS}/CLIENT_ENROLLMENT.md`}>CLIENT_ENROLLMENT.md</DocLink>
      </p>
    </Card>
  )
}
