// ABOUTME: What the system did on a lead: its events in order, each with its id, a plain label for its type, who acted, the local time and a one-line summary.
// ABOUTME: Loads the events itself and fetches them again when the page refetches; a request that fails shows a plain message.
import { getLeadEvents } from '@/api/client'
import { useRemote } from '@/api/useRemote'
import { formatTime } from '@/format'
import { ACTOR_LABELS, EVENT_LABELS } from '@/labels'

type Props = { leadId: string; refresh: number }

export function EventList({ leadId, refresh }: Props) {
  const events = useRemote(`events:${leadId}`, () => getLeadEvents(leadId), refresh)
  if (events.state === 'loading') return <p role="status">Loading events</p>
  if (events.state === 'error') return <p role="alert">{`Could not load events: ${events.message}.`}</p>
  return (
    <ol aria-label="Events" className="flex flex-col gap-1 text-sm">
      {events.data.events.map((event) => (
        <li key={event.id}>
          <span className="font-mono">{`#${event.id}`}</span>
          <span className="font-medium">{` ${EVENT_LABELS[event.type]}`}</span>
          <span className="text-muted-foreground">{` ${ACTOR_LABELS[event.actor]}, ${formatTime(event.sim_ts)}`}</span>
          {` ${event.summary}`}
        </li>
      ))}
    </ol>
  )
}
