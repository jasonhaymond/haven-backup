import { usePollRun } from '../lib/usePollRun'
import { Badge, Modal } from './ui'

const STATUS_TONE = { running: 'warning', success: 'success', failed: 'danger' }

export default function RunStatusModal({ kind, runId, title, onClose }) {
  const run = usePollRun(kind, runId)

  return (
    <Modal open={runId != null} onClose={onClose} title={title}>
      {!run ? (
        <p className="text-sm text-slate-500">Loading...</p>
      ) : (
        <div className="flex flex-col gap-3">
          <div className="flex items-center gap-2">
            <Badge tone={STATUS_TONE[run.status] ?? 'neutral'}>{run.status}</Badge>
            {kind === 'prune' && (
              <span className="text-sm text-slate-500">
                {run.dry_run ? 'Dry run' : 'Applied'} · {run.archives_deleted} archive(s) {run.dry_run ? 'would be' : ''} deleted
              </span>
            )}
          </div>
          <pre className="max-h-96 overflow-auto whitespace-pre-wrap rounded-md bg-slate-950 p-3 text-xs text-slate-100">
            {run.output_log || (run.status === 'running' ? 'Waiting for output...' : '(no output)')}
          </pre>
        </div>
      )}
    </Modal>
  )
}
