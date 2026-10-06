// ABOUTME: Tests that the narrative renders every event type, keeps one assistant message together, shows a card at its event and as one line once closed, and opens the right panel target from each chip.
// ABOUTME: Events and the lead are typed objects of the generated API types.
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { components } from '@/api/types'
import { EVENT_LABELS } from '@/labels'
import { Narrative } from './Narrative'

type Schemas = components['schemas']
type Event = Schemas['EventRow']

function event(id: number, type: Event['type'], extra: Partial<Event> = {}): Event {
  return {
    id,
    type,
    actor: 'workflow',
    mode: 'live',
    sim_ts: '2026-01-01T00:00:00Z',
    summary: `Sentence ${id}`,
    item_id: null,
    choice_ids: [],
    fact_key: null,
    message: null,
    ...extra,
  }
}

const packet: Schemas['DraftView'] = {
  intent_id: 'intent-packet',
  payload_hash: 'a'.repeat(64),
  kind: 'quote_packet',
  recipient: 'producer@example.com',
  subject: 'Your quote',
  body: 'Coverage A: $500,000',
  state: 'draft',
  round: 2,
}

const draftItem: Schemas['BlockerView'] = {
  item_id: 7,
  kind: 'underwriter_review',
  owner: 'underwriter',
  detail: {
    item_kind: 'draft',
    cause: null,
    cause_persists: false,
    resume_trigger: 'the underwriter decides',
    intent_id: packet.intent_id,
    observation_id: null,
    choice_ids: [],
    text: 'The packet is ready.',
  },
  observation: null,
}

const lead: Schemas['LeadDetail'] = {
  lead_id: 'LEAD-1',
  label: '12 Oak St',
  status: 'in_progress',
  revision: 1,
  facts: [],
  pages: [],
  plan: {
    effects: [],
    declines_on_every_branch: [],
    proposed_decline: false,
    underwriter_decline: null,
    undecided: [],
    open_choices: [],
    catalogue_questions: [],
    not_evaluated: [],
  },
  blockers: [draftItem],
  fields: [],
  drafts: [packet],
}

function narrative(events: Event[], detail = lead, onOpen = vi.fn()) {
  render(<Narrative lead={detail} events={events} onOpen={onOpen} onChange={() => {}} />)
  return onOpen
}

describe('Narrative', () => {
  it.each(Object.keys(EVENT_LABELS) as Event['type'][])('shows the sentence of a %s row', (type) => {
    narrative([event(1, type, { summary: 'The sentence.' })], { ...lead, blockers: [] })
    expect(screen.getByText('The sentence.')).toBeInTheDocument()
  })

  it('shows consecutive workflow rows as one message that a bubble, a card or another actor breaks', () => {
    narrative([
      event(1, 'plan_built'),
      event(2, 'triage_completed'),
      event(3, 'message_sent', { message: { subject: 'Hi', body: 'Body' } }),
      event(4, 'plan_built'),
      event(5, 'blocker_opened', { item_id: 7 }),
      event(6, 'plan_built'),
      event(7, 'draft_edited', { actor: 'underwriter' }),
      event(8, 'plan_built'),
    ])
    expect(screen.getAllByRole('list')).toHaveLength(4)
    expect(within(screen.getAllByRole('list')[0]).getAllByRole('listitem')).toHaveLength(2)
  })

  it('folds a long run of fact rows into one bullet that opens to them', async () => {
    narrative(Array.from({ length: 5 }, (_, i) => event(i + 1, 'fact_observed')), { ...lead, blockers: [] })
    expect(screen.getByText('Recorded 5 facts')).toBeInTheDocument()
    await userEvent.click(screen.getByText('Recorded 5 facts'))
    expect(screen.getAllByRole('button', { name: /^Event / })).toHaveLength(5)
  })

  it('shows an open item as a card at its event with its actions', () => {
    narrative([event(1, 'plan_built'), event(2, 'blocker_opened', { item_id: 7 })])
    expect(screen.getByRole('form', { name: 'Approve' })).toBeInTheDocument()
  })

  it('shows an approved item as one line and the approval once', () => {
    narrative(
      [
        event(1, 'blocker_opened', { item_id: 7 }),
        event(2, 'approval_recorded', { actor: 'underwriter', item_id: 7, summary: 'Approved the packet.' }),
      ],
      { ...lead, blockers: [] },
    )
    expect(screen.queryByRole('form', { name: 'Approve' })).toBeNull()
    expect(screen.getAllByText('The underwriter: Approved the packet.')).toHaveLength(1)
  })

  it('shows a question closed by a ruling with the ruling, and a card closed by neither as closed', () => {
    narrative(
      [
        event(1, 'blocker_opened', { item_id: 8, choice_ids: ['I13.fire_fail'] }),
        event(2, 'ruling_recorded', {
          actor: 'underwriter',
          choice_ids: ['I13.fire_fail'],
          summary: 'Decided to decline.',
        }),
        event(3, 'blocker_opened', { item_id: 9 }),
      ],
      { ...lead, blockers: [] },
    )
    expect(screen.getAllByText('The underwriter: Decided to decline.')).toHaveLength(1)
    expect(screen.getByText('Closed')).toBeInTheDocument()
  })

  it('does not show an assistant row', () => {
    narrative([event(1, 'proposal_created', { actor: 'assistant', summary: 'Assistant row.' })])
    expect(screen.queryByText('Assistant row.')).toBeNull()
  })

  it('opens an event, a fact, a reply, and a card’s details from their chips', async () => {
    const onOpen = narrative([
      event(1, 'plan_built'),
      event(2, 'fact_observed'),
      event(3, 'message_sent', { message: { subject: 'Ask', body: 'Please send it.' } }),
      event(4, 'reply_received', { message: { subject: null, body: 'Here it is.' } }),
      event(5, 'blocker_opened', { item_id: 7 }),
    ])
    const chips = screen.getAllByRole('button', { name: /^Event / })
    for (const chip of chips) await userEvent.click(chip)
    await userEvent.click(screen.getByRole('button', { name: 'details' }))

    expect(onOpen.mock.calls.map(([target]) => target)).toEqual([
      { kind: 'event', lead_id: 'LEAD-1', id: 1 },
      { kind: 'fact', lead_id: 'LEAD-1', id: 2 },
      { kind: 'event', lead_id: 'LEAD-1', id: 3 },
      { kind: 'reply', lead_id: 'LEAD-1', id: 4 },
      { kind: 'event', lead_id: 'LEAD-1', id: 5 },
    ])
  })
})
