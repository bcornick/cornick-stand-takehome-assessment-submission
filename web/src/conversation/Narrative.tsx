// ABOUTME: A lead's timeline as a conversation: what the system did as assistant messages, the messages sent and received as bubbles, and the underwriter's items as cards at their event.
// ABOUTME: Built from the lead's events, oldest first.
import type { components } from '@/api/types'
import type { PanelTarget } from '@/surface'

type Schemas = components['schemas']

type Props = {
  lead: Schemas['LeadDetail']
  events: Schemas['EventRow'][]
  onOpen: (target: PanelTarget) => void
  onChange: () => void
}

export function Narrative({ events }: Props) {
  return (
    <ol>
      {events.map((event) => (
        <li key={event.id}>{event.summary}</li>
      ))}
    </ol>
  )
}
