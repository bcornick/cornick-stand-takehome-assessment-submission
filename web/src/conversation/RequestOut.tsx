// ABOUTME: The card under a waiting lead's summary: the request to the producer that is out, its round, when it went out in simulated time and how long ago, what it asks, and a link to the message.
// ABOUTME: It reads the lead's drafts, so a lead with no request out shows nothing.
import type { components } from '@/api/types'
import { formatTime } from '@/format'
import type { PanelTarget } from '@/surface'

type Schemas = components['schemas']

type Props = {
  lead: Schemas['LeadDetail']
  simNow: string | null // the simulated time now; null when no run is loaded
  onOpen: (target: PanelTarget) => void
}

// The span from `from` to `to` as the largest whole unit, for example "3 hours ago".
function ago(from: string, to: string): string {
  const minutes = Math.floor((new Date(to).getTime() - new Date(from).getTime()) / 60_000)
  const [count, unit] =
    minutes >= 1440 ? [Math.floor(minutes / 1440), 'day'] : minutes >= 60 ? [Math.floor(minutes / 60), 'hour'] : [Math.max(minutes, 0), 'minute']
  return `${count} ${unit}${count === 1 ? '' : 's'} ago`
}

export function RequestOut({ lead, simNow, onOpen }: Props) {
  const waiting = lead.blockers.some((blocker) => blocker.kind === 'producer_reply')
  const request = lead.drafts.findLast(
    (draft) => draft.state === 'sent' && (draft.kind === 'routine_request' || draft.kind === 'sensitive_request'),
  )
  if (!waiting || request === undefined) return null
  return (
    <section aria-label="Request to the producer" className="flex flex-col gap-2 rounded-md border bg-background p-3 text-sm">
      <p>
        <span className="font-medium">{`Round ${request.round}`}</span>
        {request.sent_at !== null && ` · sent ${formatTime(request.sent_at)}`}
        {request.sent_at !== null && simNow !== null && ` (${ago(request.sent_at, simNow)})`}
      </p>
      <div className="flex flex-col gap-1">
        <p className="text-muted-foreground">Asks for:</p>
        <ul aria-label="Asks" className="list-disc pl-5">
          {request.asks.map((ask) => (
            <li key={ask}>{ask}</li>
          ))}
        </ul>
      </div>
      <button
        type="button"
        className="button-outline self-start"
        onClick={() => onOpen({ kind: 'message', lead_id: lead.lead_id, id: request.intent_id })}
      >
        View the request
      </button>
    </section>
  )
}
