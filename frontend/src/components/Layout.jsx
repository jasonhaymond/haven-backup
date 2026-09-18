import { useEffect, useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { api } from '../lib/api'

const navItems = [
  { to: '/', label: 'Dashboard', end: true },
  { to: '/repos', label: 'Repositories' },
  { to: '/hosts', label: 'Client Hosts' },
  { to: '/credentials', label: 'SSH Credentials' },
]

export default function Layout() {
  const { user, logout } = useAuth()
  const [versionInfo, setVersionInfo] = useState(null)

  useEffect(() => {
    api.get('/version').then(setVersionInfo).catch(() => setVersionInfo(null))
  }, [])

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 dark:bg-slate-950 dark:text-slate-100">
      <div className="mx-auto flex max-w-6xl gap-6 px-4 py-6">
        <aside className="w-56 shrink-0">
          <div className="mb-6 px-2 text-lg font-semibold tracking-tight">Haven Backup</div>
          <nav className="flex flex-col gap-1">
            {navItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  `rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                    isActive
                      ? 'bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900'
                      : 'text-slate-600 hover:bg-slate-200/60 dark:text-slate-300 dark:hover:bg-slate-800'
                  }`
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
          <div className="mt-8 border-t border-slate-200 px-2 pt-4 text-sm dark:border-slate-800">
            <div className="mb-2 text-slate-500 dark:text-slate-400">{user?.username}</div>
            <button
              onClick={logout}
              className="text-slate-600 underline decoration-slate-300 underline-offset-2 hover:text-slate-900 dark:text-slate-300 dark:hover:text-white"
            >
              Sign out
            </button>
          </div>
          <div className="mt-6 px-2 text-xs text-slate-400 dark:text-slate-600">
            v{__APP_VERSION__}
            {versionInfo?.update_available && (
              <span
                className="ml-1.5 rounded-full bg-amber-100 px-1.5 py-0.5 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300"
                title={`Update available: ${versionInfo.latest}. Run scripts/update.sh on the host to deploy it.`}
              >
                {versionInfo.latest} available
              </span>
            )}
          </div>
        </aside>
        <main className="min-w-0 flex-1 pb-16">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
