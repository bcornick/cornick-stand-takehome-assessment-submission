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
    lookup: null,
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
  asks: [],
  sent_at: null,
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
  summary: 'Triage is running.',  revision: 1,
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
  readings: {},
  fields: [],
  missing_fields: [],
  decline_reason: null,
  drafts: [packet],
}

function narrative(events: Event[], detail = lead, onOpen = vi.fn()) {
  render(<Narrative lead={detail} events={events} onOpen={onOpen} />)
  return onOpen
}

describe('Narrative', () => {
const notNarrated: Event['type'][] = ['model_called', 'skill_fallback_used', 'replay_miss', 'fault_injected', 'provider_called']

  it.each((Object.keys(EVENT_LABELS) as Event['type'][]).filter((type) => !notNarrated.includes(type)))('shows the sentence of a %s row', (type) => {
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
    expect(screen.getAllByRole('button', { name: /^Open fact / })).toHaveLength(5)
  })

  it('shows an open item at its event as its line, since its card sits above the fold', () => {
    narrative([event(1, 'plan_built'), event(2, 'blocker_opened', { item_id: 7, summary: 'Waiting on you.' })])
    expect(screen.getByText('Waiting on you.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Send quote' })).toBeNull()
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

  it('opens a fact, a message and a reply from their chips', async () => {
    const onOpen = narrative([
      event(1, 'plan_built'),
      event(2, 'fact_observed', { fact_key: 'roof_year' }),
      event(3, 'message_sent', { message: { subject: 'Ask', body: 'Please send it.' } }),
      event(4, 'reply_received', { message: { subject: null, body: 'Here it is.' } }),
      event(5, 'blocker_opened', { item_id: 7 }),
    ])
    await userEvent.click(screen.getByRole('button', { name: 'Open fact roof_year' }))
    await userEvent.click(screen.getByRole('button', { name: 'Open the message' }))
    await userEvent.click(screen.getByRole('button', { name: 'Open the reply' }))

    expect(onOpen.mock.calls.map(([target]) => target)).toEqual([
      { kind: 'fact', lead_id: 'LEAD-1', id: 2 },
      { kind: 'event', lead_id: 'LEAD-1', id: 3 },
      { kind: 'reply', lead_id: 'LEAD-1', id: 4 },
    ])
  })

  it('numbers fact chips within each message and gives a plan line none', () => {
    narrative(
      [
        event(1, 'plan_built'),
        event(2, 'fact_observed', { fact_key: 'a' }),
        event(3, 'fact_observed', { fact_key: 'b' }),
        event(4, 'message_sent', { message: { subject: 'Hi', body: 'Body' } }),
        event(5, 'fact_observed', { fact_key: 'c' }),
      ],
      { ...lead, blockers: [] },
    )
    const chips = screen.getAllByRole('button').map((chip) => `${chip.getAttribute('aria-label')}=${chip.textContent}`)
    expect(chips).toEqual(['Open fact a=fact', 'Open fact b=fact', 'Open the message=email', 'Open fact c=fact'])
  })

  it('shows a run of provider lookups as one sentence with counts and labelled missing inputs', () => {
    const lookup = (status: 'found' | 'not_found' | 'blocked' | 'unavailable', missing: string[] = []) => ({
      status,
      missing_inputs: missing,
    })
    narrative(
      [
        event(1, 'provider_called', { lookup: lookup('found') }),
        event(2, 'provider_called', { lookup: lookup('found') }),
        event(3, 'provider_called', { lookup: lookup('blocked', ['city', 'zip']) }),
        event(4, 'provider_called', { lookup: lookup('blocked', ['city']) }),
        event(5, 'provider_called', { lookup: lookup('not_found') }),
        event(6, 'provider_called', { lookup: lookup('unavailable') }),
      ],
      {
        ...lead,
        blockers: [],
        fields: [
          { key: 'city', label: 'City' },
          { key: 'zip', label: 'ZIP code' },
        ] as Schemas['LeadDetail']['fields'],
      },
    )
    expect(
      screen.getByText('Looked up 6 providers: 2 found, 2 blocked on City and ZIP code, 1 not found, 1 unavailable'),
    ).toBeInTheDocument()
  })

  it('omits a count that is zero', () => {
    narrative([event(1, 'provider_called', { lookup: { status: 'found', missing_inputs: [] } })], { ...lead, blockers: [] })
    expect(screen.getByText('Looked up 1 provider: 1 found')).toBeInTheDocument()
  })

  it('shows the last triage line of a run only', () => {
    narrative(
      [event(1, 'triage_completed', { summary: 'First.' }), event(2, 'triage_completed', { summary: 'Last.' })],
      { ...lead, blockers: [] },
    )
    expect(screen.queryByText('First.')).toBeNull()
    expect(screen.getByText('Last.')).toBeInTheDocument()
  })

  it('shows field keys in a sentence as registry labels', () => {
    narrative([event(1, 'plan_built', { summary: 'Checked p_f.' })], {
      ...lead,
      blockers: [],
      fields: [{ key: 'p_f', label: 'Fire probability' }] as Schemas['LeadDetail']['fields'],
    })
    expect(screen.getByText('Checked Fire probability.')).toBeInTheDocument()
  })

  it('labels each assistant message', () => {
    narrative([event(1, 'plan_built')], { ...lead, blockers: [] })
    expect(screen.getByText('Assistant')).toBeInTheDocument()
  })
})
