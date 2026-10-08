// ABOUTME: The demo controls, apart from the product: load the day's leads and deliver the producers' fixture replies.
// ABOUTME: A small console in the Terminal's black and green, pinned to the bottom right corner beside the composer, so it reads as apart from the app; it starts as a tab reading "Demo controls" and opens on a click.
import { useState } from 'react'
import type { components } from '@/api/types'
import { deliverFixtureReplies, startRun } from '@/api/client'
import { ActionButton } from '@/components/ActionButton'

type Props = { run: components['schemas']['RunView']; onChange: () => void }

export function DemoPanel({ run, onChange }: Props) {
  const [minimised, setMinimised] = useState(true)
  const [confirming, setConfirming] = useState(false)
  const runId = run.run_id ?? 'No run loaded'

  // The confirm closes once the start has answered, so its button shows the start running or failing.
  const load = async () => {
    await startRun()
    setConfirming(false)
    return null
  }
  const deliver = async () =>
    (await deliverFixtureReplies()).replies.find((reply) => !reply.accepted)?.reason ?? null

  if (minimised) {
    return (
      <aside aria-label="Demo controls" className="fixed bottom-4 right-4 z-10">
        <button
          type="button"
          onClick={() => setMinimised(false)}
          className="console border border-console-ink bg-console px-3 py-1 font-console text-xs text-console-ink"
        >
          Demo controls
        </button>
      </aside>
    )
  }

  return (
    <aside
      aria-label="Demo controls"
      className="console fixed bottom-4 right-4 z-10 w-72 space-y-3 border border-console-ink bg-console p-4 font-console text-sm text-console-ink"
    >
      <div className="flex items-center justify-between">
        <h2>Demo controls</h2>
        <button type="button" onClick={() => setMinimised(true)} className="text-xs text-console-ink/70">
          Minimise
        </button>
      </div>
      <dl className="text-xs text-console-ink/70">
        <div>Mode: {run.mode}</div>
        <div>Seed: {run.seed}</div>
        <div>{runId}</div>
      </dl>
      {confirming ? (
        <div className="space-y-2">
          <p>This clears the current day</p>
          <div className="flex gap-2">
            <ActionButton label="Load anyway" act={load} onDone={onChange} />
            <button
              type="button"
              onClick={() => setConfirming(false)}
              className="button-outline"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : run.run_id === null ? (
        <ActionButton label="Load today's leads" act={load} onDone={onChange} />
      ) : (
        <button
          type="button"
          onClick={() => setConfirming(true)}
          className="button-primary"
        >
          Load today's leads
        </button>
      )}
      <ActionButton label="Deliver the producers' replies" act={deliver} onDone={onChange} />
    </aside>
  )
}
