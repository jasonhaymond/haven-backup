import { useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { Button, Card, ErrorText, Input } from '../components/ui'

export default function Login() {
  const { login } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await login(username, password)
    } catch (err) {
      setError(err.status === 401 ? 'Invalid username or password' : err.message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 dark:bg-slate-950">
      <Card className="w-full max-w-sm">
        <h1 className="mb-4 text-lg font-semibold">Haven Backup</h1>
        <form onSubmit={handleSubmit} className="flex flex-col gap-3">
          <Input label="Username" value={username} onChange={(e) => setUsername(e.target.value)} required autoFocus />
          <Input label="Password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
          <ErrorText>{error}</ErrorText>
          <Button type="submit" disabled={submitting}>{submitting ? 'Signing in...' : 'Sign in'}</Button>
        </form>
      </Card>
    </div>
  )
}
