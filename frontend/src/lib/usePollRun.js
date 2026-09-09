import { useEffect, useState } from 'react'
import { api } from './api'

const ENDPOINTS = { backup: '/runs/backups', prune: '/runs/prunes', check: '/runs/checks' }

/** Polls a run record every 2s while it's still "running". Returns the latest run, or null. */
export function usePollRun(kind, runId) {
  const [run, setRun] = useState(null)

  useEffect(() => {
    if (!runId) {
      setRun(null)
      return
    }
    let cancelled = false
    let timer

    async function poll() {
      try {
        const data = await api.get(`${ENDPOINTS[kind]}/${runId}`)
        if (cancelled) return
        setRun(data)
        if (data.status === 'running') {
          timer = setTimeout(poll, 2000)
        }
      } catch {
        // transient fetch error -- keep the last known state, try again shortly
        if (!cancelled) timer = setTimeout(poll, 3000)
      }
    }
    poll()

    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [kind, runId])

  return run
}
