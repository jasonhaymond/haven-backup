import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { Button, Card, ErrorText, Input, Textarea } from '../components/ui'

const emptyForm = { name: '', hostname: '', port: 22, username: '', private_key: '', key_passphrase: '' }

export default function Credentials() {
  const [credentials, setCredentials] = useState(null)
  const [form, setForm] = useState(emptyForm)
  const [showForm, setShowForm] = useState(false)
  const [error, setError] = useState(null)
  const [submitting, setSubmitting] = useState(false)

  function load() {
    api.get('/credentials').then(setCredentials).catch((e) => setError(e.message))
  }

  useEffect(load, [])

  async function handleSubmit(e) {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await api.post('/credentials', { ...form, port: Number(form.port) })
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
    if (!confirm('Delete this credential? Anything using it will stop working.')) return
    await api.delete(`/credentials/${id}`)
    load()
  }

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-xl font-semibold">SSH Credentials</h1>
        <Button onClick={() => setShowForm((v) => !v)}>{showForm ? 'Cancel' : 'Add credential'}</Button>
      </div>

      {showForm && (
        <Card className="mb-4">
          <form onSubmit={handleSubmit} className="grid grid-cols-2 gap-3">
            <Input label="Name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
            <Input label="Hostname" value={form.hostname} onChange={(e) => setForm({ ...form, hostname: e.target.value })} required />
            <Input label="Port" type="number" value={form.port} onChange={(e) => setForm({ ...form, port: e.target.value })} required />
            <Input label="Username" value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} required />
            <div className="col-span-2">
              <Textarea
                label="Private key (PEM)"
                rows={6}
                value={form.private_key}
                onChange={(e) => setForm({ ...form, private_key: e.target.value })}
                required
                className="w-full"
              />
            </div>
            <Input
              label="Key passphrase (if the key itself is encrypted)"
              type="password"
              value={form.key_passphrase}
              onChange={(e) => setForm({ ...form, key_passphrase: e.target.value })}
            />
            <ErrorText>{error}</ErrorText>
            <div className="col-span-2">
              <Button type="submit" disabled={submitting}>{submitting ? 'Saving...' : 'Save credential'}</Button>
            </div>
          </form>
        </Card>
      )}

      <Card>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-left text-slate-500 dark:border-slate-800 dark:text-slate-400">
              <th className="py-2">Name</th>
              <th>Host</th>
              <th>User</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {(credentials ?? []).map((c) => (
              <tr key={c.id} className="border-b border-slate-100 last:border-0 dark:border-slate-800">
                <td className="py-2">{c.name}</td>
                <td>{c.hostname}:{c.port}</td>
                <td>{c.username}</td>
                <td className="text-right">
                  <button onClick={() => handleDelete(c.id)} className="text-red-600 hover:underline dark:text-red-400">
                    Delete
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {credentials && credentials.length === 0 && <p className="py-2 text-sm text-slate-500">No credentials yet.</p>}
      </Card>
    </div>
  )
}
