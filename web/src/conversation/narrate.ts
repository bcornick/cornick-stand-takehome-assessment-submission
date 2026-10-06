// ABOUTME: Groups a lead's events, oldest first, into the blocks of its conversation: assistant messages, bubbles, item cards and the underwriter's own lines.
// ABOUTME: A resolved card absorbs the row that closed it, and the assistant's own rows and the system's run records are left out, so the narrative says each thing once.
import type { components } from '@/api/types'

type Schemas = components['schemas']
type Event = Schemas['EventRow']
type Lead = Schemas['LeadDetail']
type Message = NonNullable<Event['message']>

// Rows that record how the system ran rather than what it did for the lead.
const HIDDEN_TYPES: Event['type'][] = ['model_called', 'skill_fallback_used', 'replay_miss', 'fault_injected']

// A run of fact rows longer than this folds into one bullet.
const FACT_RUN_LIMIT = 3
const FACT_TYPES: Event['type'][] = ['fact_observed', 'fact_selected']

export type Bullet =
  | { kind: 'event'; event: Event }
  | { kind: 'facts'; events: Event[] }
  | { kind: 'lookups'; events: Event[] }

export type Block =
  | { kind: 'open_card'; event: Event }
  | { kind: 'resolved_card'; event: Event; closing: Event | null }
  | { kind: 'bubble'; event: Event; message: Message }
  | { kind: 'assistant_message'; bullets: Bullet[] }
  | { kind: 'line'; event: Event }

// The row that shows how a card closed: the approval of its item, else the first later ruling on one of its choices.
function closingRow(card: Event, later: Event[]): Event | null {
  const approval = later.find((e) => e.type === 'approval_recorded' && e.item_id === card.item_id)
  if (approval) return approval
  return (
    later.find(
      (e) => e.type === 'ruling_recorded' && e.choice_ids.some((choice) => card.choice_ids.includes(choice)),
    ) ?? null
  )
}

// One message's rows as bullets: a run of provider lookups is one bullet, a run of triage rows keeps its last, a long run of facts folds.
function bulletsOf(events: Event[]): Bullet[] {
  const bullets: Bullet[] = []
  let index = 0
  while (index < events.length) {
    const type = events[index].type
    const sameRun = (other: Event['type']) => other === type || (FACT_TYPES.includes(type) && FACT_TYPES.includes(other))
    let end = index
    while (end < events.length && sameRun(events[end].type)) end += 1
    const run = events.slice(index, end)
    if (type === 'provider_called') {
      bullets.push({ kind: 'lookups', events: run })
    } else if (type === 'triage_completed') {
      bullets.push({ kind: 'event', event: run[run.length - 1] })
    } else if (FACT_TYPES.includes(type) && run.length > FACT_RUN_LIMIT) {
      bullets.push({ kind: 'facts', events: run })
    } else {
      bullets.push(...run.map((event): Bullet => ({ kind: 'event', event })))
    }
    index = end
  }
  return bullets
}

export function narrate(events: Event[], lead: Lead): Block[] {
  const shownOnCards = new Set<number>()
  const closings = new Map<number, Event | null>()
  events.forEach((event, index) => {
    if (event.type !== 'blocker_opened' || event.item_id === null) return
    if (lead.blockers.some((b) => b.item_id === event.item_id)) return
    const closing = closingRow(event, events.slice(index + 1))
    if (closing) shownOnCards.add(closing.id)
    closings.set(event.id, closing)
  })

  const blocks: Block[] = []
  let pending: Event[] = []
  const flush = () => {
    if (pending.length) blocks.push({ kind: 'assistant_message', bullets: bulletsOf(pending) })
    pending = []
  }

  for (const event of events) {
    if (event.actor === 'assistant' || HIDDEN_TYPES.includes(event.type) || shownOnCards.has(event.id)) continue
    if (event.type === 'blocker_closed' && event.item_id !== null) continue
    if (event.type === 'blocker_opened' && event.item_id !== null) {
      flush()
      const open = lead.blockers.some((b) => b.item_id === event.item_id)
      blocks.push(
        open
          ? { kind: 'open_card', event }
          : { kind: 'resolved_card', event, closing: closings.get(event.id) ?? null },
      )
    } else if ((event.type === 'message_sent' || event.type === 'reply_received') && event.message) {
      flush()
      blocks.push({ kind: 'bubble', event, message: event.message })
    } else if (event.actor !== 'underwriter') {
      // Reading a reply is the system's work too, written under the actor that delivered it.
      pending.push(event)
    } else {
      flush()
      blocks.push({ kind: 'line', event })
    }
  }
  flush()
  return blocks
}
