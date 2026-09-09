import { Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider, useAuth } from './context/AuthContext'
import Layout from './components/Layout'
import Setup from './pages/Setup'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Repos from './pages/Repos'
import RepoDetail from './pages/RepoDetail'
import Hosts from './pages/Hosts'
import Credentials from './pages/Credentials'

function Gate() {
  const { user, setupRequired, loading } = useAuth()

  if (loading) return null
  if (setupRequired) return <Setup />
  if (!user) return <Login />

  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Dashboard />} />
        <Route path="/repos" element={<Repos />} />
        <Route path="/repos/:repoId" element={<RepoDetail />} />
        <Route path="/hosts" element={<Hosts />} />
        <Route path="/credentials" element={<Credentials />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <Gate />
    </AuthProvider>
  )
}
