// ABOUTME: A lead's timeline as a conversation: what the system did as assistant messages, the messages sent and received as bubbles, and the underwriter's items as cards at their event.
// ABOUTME: Built from the lead's events, oldest first.
import type { components } from '@/api/types'
import { Chip } from '@/components/Chip'
import { formatTime } from '@/format'
import { ACTOR_LABELS } from '@/labels'
import { OpenItem } from '@/lead/ItemActions'
import type { PanelTarget } from '@/surface'
import { type Block, type Bullet, narrate } from './narrate'

type Schemas = components['schemas']
type Event = Schemas['EventRow']

type Props = {
  lead: Schemas['LeadDetail']
  events: Schemas['EventRow'][]
  onOpen: (target: PanelTarget) => void
  onChange: () => void
}

type Open = (target: PanelTarget) => void

function EventChip({ event, leadId, onOpen }: { event: Event; leadId: string; onOpen: Open }) {
  const kind = event.type === 'fact_observed' ? 'fact' : 'event'
  return (
    <Chip
      label={event.id}
      opens={`Event ${event.id}`}
      onClick={() => onOpen({ kind, lead_id: leadId, id: event.id })}
    />
  )
}

function BulletRow({ bullet, leadId, onOpen }: { bullet: Bullet; leadId: string; onOpen: Open }) {
  if (bullet.kind === 'event') {
    return (
      <li className="flex items-baseline gap-2">
        <span>{bullet.event.summary}</span>
        <EventChip event={bullet.event} leadId={leadId} onOpen={onOpen} />
      </li>
    )
  }
  return (
    <li>
      <details>
        <summary>{`Recorded ${bullet.events.length} facts`}</summary>
        <ul className="mt-1 flex flex-col gap-1 pl-4">
          {bullet.events.map((event) => (
            <BulletRow key={event.id} bullet={{ kind: 'event', event }} leadId={leadId} onOpen={onOpen} />
          ))}
        </ul>
      </details>
    </li>
  )
}

function BlockView({ block, lead, onOpen, onChange }: { block: Block } & Omit<Props, 'events'>) {
  const leadId = lead.lead_id
  switch (block.kind) {
    case 'assistant_message':
      return (
        <ul className="flex flex-col gap-1">
          {block.bullets.map((bullet) => (
            <BulletRow
              key={bullet.kind === 'event' ? bullet.event.id : bullet.events[0].id}
              bullet={bullet}
              leadId={leadId}
              onOpen={onOpen}
            />
          ))}
        </ul>
      )
    case 'open_card':
      return (
        <div className="flex flex-col gap-2 rounded-md border bg-background p-3">
          <OpenItem lead={lead} blocker={block.blocker} onChange={onChange} />
          <button
            type="button"
            className="self-start text-sm underline"
            onClick={() => onOpen({ kind: 'event', lead_id: leadId, id: block.event.id })}
          >
            details
          </button>
        </div>
      )
    case 'resolved_card':
      return (
        <p className="text-sm text-gray-600">
          {block.closing ? `${ACTOR_LABELS[block.closing.actor]}: ${block.closing.summary}` : 'Closed'}
        </p>
      )
    case 'bubble': {
      const sent = block.event.type === 'message_sent'
      const { subject, body } = block.message
      // The body folds under its first line; a one-line body has nothing to fold.
      const [firstLine, ...rest] = body.split('\n')
      return (
        <div className="flex flex-col gap-1 rounded-md border bg-background p-3">
          <p className="flex items-baseline gap-2 text-sm text-gray-600">
            <span>{sent ? 'To the producer' : 'From the producer'}</span>
            <span>{formatTime(block.event.sim_ts)}</span>
            <Chip
              label={block.event.id}
              opens={`Event ${block.event.id}`}
              onClick={() => onOpen({ kind: sent ? 'event' : 'reply', lead_id: leadId, id: block.event.id })}
            />
          </p>
          {subject && <p className="font-medium">{subject}</p>}
          {rest.length === 0 ? (
            <p>{firstLine}</p>
          ) : (
            <details>
              <summary>{firstLine}</summary>
              <p className="mt-1 whitespace-pre-wrap">{rest.join('\n').trim()}</p>
            </details>
          )}
        </div>
      )
    }
    case 'line':
      return (
        <p className="flex items-baseline gap-2">
          <span className="text-sm text-gray-600">{ACTOR_LABELS[block.event.actor]}</span>
          <span>{block.event.summary}</span>
          <EventChip event={block.event} leadId={leadId} onOpen={onOpen} />
        </p>
      )
  }
}

export function Narrative({ lead, events, onOpen, onChange }: Props) {
  return (
    <div className="flex flex-col gap-3">
      {narrate(events, lead).map((block, index) => (
        <BlockView key={index} block={block} lead={lead} onOpen={onOpen} onChange={onChange} />
      ))}
    </div>
  )
}
