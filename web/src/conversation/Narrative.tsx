// ABOUTME: A lead's timeline as a conversation: what the system did as assistant messages, the messages sent and received as bubbles, and the underwriter's items as cards at their event.
// ABOUTME: Built from the lead's events, oldest first.
import type { components } from '@/api/types'
import { Chip } from '@/components/Chip'
import { formatTime, labelKeys } from '@/format'
import { ACTOR_LABELS } from '@/labels'
import type { PanelTarget } from '@/surface'
import { type Block, type Bullet, narrate } from './narrate'

type Schemas = components['schemas']
type Event = Schemas['EventRow']

type Props = {
  lead: Schemas['LeadDetail']
  events: Schemas['EventRow'][]
  onOpen: (target: PanelTarget) => void
}

type Open = (target: PanelTarget) => void
type Lead = Schemas['LeadDetail']

const plural = (count: number, noun: string) => `${count} ${noun}${count === 1 ? '' : 's'}`

function joinWithAnd(items: string[]): string {
  return items.length < 2 ? items.join('') : `${items.slice(0, -1).join(', ')} and ${items[items.length - 1]}`
}

// A run of provider lookups as one sentence: how many, how each went, and which inputs the blocked ones lacked.
function lookupSentence(events: Event[], lead: Lead): string {
  const lookups = events.flatMap((event) => (event.lookup ? [event.lookup] : []))
  const count = (status: string) => lookups.filter((lookup) => lookup.status === status).length
  const missing = [...new Set(lookups.flatMap((lookup) => lookup.missing_inputs))]
  const blocked = count('blocked')
  const outcomes = [
    count('found') && `${count('found')} found`,
    blocked && `${blocked} blocked on ${joinWithAnd(missing.map((key) => labelKeys(key, lead.fields)))}`,
    count('not_found') && `${count('not_found')} not found`,
    count('unavailable') && `${count('unavailable')} unavailable`,
  ].filter(Boolean)
  return `Looked up ${plural(events.length, 'provider')}: ${outcomes.join(', ')}`
}


type BulletProps = { bullet: Bullet; lead: Lead; onOpen: Open }

function BulletRow({ bullet, lead, onOpen }: BulletProps) {
  if (bullet.kind === 'lookups') return <li>{lookupSentence(bullet.events, lead)}</li>
  if (bullet.kind === 'facts') {
    return (
      <li>
        <details>
          <summary>{`Recorded ${bullet.events.length} facts`}</summary>
          <ul className="mt-1 flex flex-col gap-1 pl-4">
            {bullet.events.map((event) => (
              <BulletRow key={event.id} bullet={{ kind: 'event', event }} lead={lead} onOpen={onOpen} />
            ))}
          </ul>
        </details>
      </li>
    )
  }
  const { event } = bullet
  return (
    <li className="flex items-baseline gap-2">
      <span>{labelKeys(event.summary, lead.fields)}</span>
      {event.type === 'fact_observed' && (
        <Chip
          label="fact"
          opens={`Open fact ${event.fact_key ?? event.id}`}
          onClick={() => onOpen({ kind: 'fact', lead_id: lead.lead_id, id: event.id })}
        />
      )}
    </li>
  )
}

function BlockView({ block, lead, onOpen }: { block: Block } & Omit<Props, 'events'>) {
  const leadId = lead.lead_id
  switch (block.kind) {
    case 'assistant_message': {
      return (
        <div className="flex flex-col gap-1 text-sm">
          <p className="text-xs text-gray-600">Assistant</p>
          <ul className="flex flex-col gap-1">
            {block.bullets.map((bullet) => (
              <BulletRow key={bullet.kind === 'event' ? bullet.event.id : bullet.events[0].id} bullet={bullet} lead={lead} onOpen={onOpen} />
            ))}
          </ul>
        </div>
      )
    }
    case 'open_card':
      // The card itself sits above the fold, after the summary; the timeline keeps the line.
      return <p className="text-sm">{labelKeys(block.event.summary, lead.fields)}</p>
    case 'resolved_card':
      return (
        <p className="text-sm text-gray-600">
          {block.closing
            ? `${ACTOR_LABELS[block.closing.actor]}: ${labelKeys(block.closing.summary, lead.fields)}`
            : 'Closed'}
        </p>
      )
    case 'bubble': {
      const sent = block.event.type === 'message_sent'
      const { subject, body } = block.message
      // The body folds under its first line; a one-line body has nothing to fold.
      const [firstLine, ...rest] = body.split('\n')
      return (
        <div className="flex flex-col gap-1 rounded-md border bg-background p-3 text-sm">
          <p className="flex items-baseline gap-2 text-xs text-gray-600">
            <span>{sent ? 'To the producer' : 'From the producer'}</span>
            <span>{formatTime(block.event.sim_ts)}</span>
            <Chip
              label={sent ? 'email' : 'reply'}
              opens={sent ? 'Open the message' : 'Open the reply'}
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
        <p className="flex items-baseline gap-2 text-sm">
          <span className="text-xs text-gray-600">{ACTOR_LABELS[block.event.actor]}</span>
          <span>{labelKeys(block.event.summary, lead.fields)}</span>
        </p>
      )
  }
}

export function Narrative({ lead, events, onOpen }: Props) {
  return (
    <div className="flex flex-col gap-5">
      {narrate(events, lead).map((block, index) => (
        <BlockView key={index} block={block} lead={lead} onOpen={onOpen} />
      ))}
    </div>
  )
}
