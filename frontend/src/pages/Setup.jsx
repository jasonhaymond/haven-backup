import { useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { Button, Card, ErrorText, Input } from '../components/ui'

export default function Setup() {
  const { setup } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    setError(null)
    if (password !== confirm) {
      setError('Passwords do not match')
      return
    }
    setSubmitting(true)
    try {
      await setup(username, password)
    } catch (err) {
      setError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 dark:bg-slate-950">
      <Card className="w-full max-w-sm">
        <h1 className="mb-1 text-lg font-semibold">Welcome to Haven Backup</h1>
        <p className="mb-4 text-sm text-slate-500 dark:text-slate-400">Create the first admin account to get started.</p>
        <form onSubmit={handleSubmit} className="flex flex-col gap-3">
          <Input label="Username" value={username} onChange={(e) => setUsername(e.target.value)} required autoFocus />
          <Input label="Password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={8} />
          <Input label="Confirm password" type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} required minLength={8} />
          <ErrorText>{error}</ErrorText>
          <Button type="submit" disabled={submitting}>{submitting ? 'Creating...' : 'Create admin account'}</Button>
        </form>
      </Card>
    </div>
  )
}
