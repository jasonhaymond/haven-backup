import { useState } from 'react'

/** Collapsible, per-page contextual help. Collapse state is remembered per
 * viewer (localStorage) so it doesn't reappear every visit once dismissed,
 * but defaults open -- someone landing on a page for the first time should
 * see it without having to know to look for it. */
export function HelpBox({ id, title, children, defaultOpen = true }) {
  const storageKey = `haven-help-${id}`
  const [open, setOpen] = useState(() => {
    try {
      const stored = window.localStorage.getItem(storageKey)
      return stored === null ? defaultOpen : stored === 'open'
    } catch {
      return defaultOpen
    }
  })

  function toggle() {
    setOpen((prev) => {
      const next = !prev
      try {
        window.localStorage.setItem(storageKey, next ? 'open' : 'closed')
      } catch {
        // localStorage unavailable (private browsing, etc.) -- state just won't persist
      }
      return next
    })
  }

  return (
    <div className="mb-4 rounded-lg border border-sky-200 bg-sky-50 dark:border-sky-900 dark:bg-sky-950/40">
      <button
        onClick={toggle}
        className="flex w-full items-center justify-between px-4 py-2.5 text-left text-sm font-medium text-sky-900 dark:text-sky-200"
      >
        <span>{title}</span>
        <span className="text-xs font-normal text-sky-600 dark:text-sky-400">{open ? 'Hide help' : 'Show help'}</span>
      </button>
      {open && (
        <div className="space-y-2 border-t border-sky-200 px-4 py-3 text-sm text-sky-950 dark:border-sky-900 dark:text-sky-100">
          {children}
        </div>
      )}
    </div>
  )
}

export function Steps({ children }) {
  return <ol className="list-decimal space-y-1.5 pl-5">{children}</ol>
}
