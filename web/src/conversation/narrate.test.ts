// ABOUTME: Tests how a lead's events group into conversation blocks: assistant messages, folded fact runs, cards and what closed them, bubbles and other actors' lines.
// ABOUTME: Events and the lead are typed objects of the generated API types.
import { describe, expect, it } from 'vitest'
import type { components } from '@/api/types'
import { narrate } from './narrate'

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

const noDetail: Schemas['BlockerDetail'] = {
  item_kind: null,
  cause: null,
  cause_persists: false,
  resume_trigger: 'the underwriter decides',
  intent_id: null,
  observation_id: null,
  choice_ids: [],
  text: '',
}

function leadWith(blockers: Schemas['LeadDetail']['blockers']): Schemas['LeadDetail'] {
  return {
    lead_id: 'LEAD-1',
    label: '12 Oak St',
    status: 'in_progress',
    summary: 'Triage is running.',    revision: 1,
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
    blockers,
    readings: {},
    fields: [],
    missing_fields: [],
  decline_reason: null,
    drafts: [],
  }
}

const openItem: Schemas['BlockerView'] = {
  item_id: 7,
  kind: 'underwriter_review',
  owner: 'underwriter',
  detail: { ...noDetail, item_kind: 'review', text: 'A review.' },
  observation: null,
}

const kinds = (events: Event[], blockers: Schemas['LeadDetail']['blockers'] = []) =>
  narrate(events, leadWith(blockers)).map((b) => b.kind)

describe('narrate', () => {
  it('leaves out assistant rows and the close of an underwriter item', () => {
    const events = [
      event(1, 'proposal_created', { actor: 'assistant' }),
      event(2, 'blocker_closed', { item_id: 7 }),
    ]
    expect(kinds(events)).toEqual([])
  })

  it.each(['model_called', 'skill_fallback_used', 'replay_miss', 'fault_injected'] as const)(
    'leaves out a %s row without breaking the message around it',
    (type) => {
      const events = [event(1, 'plan_built'), event(2, type), event(3, 'plan_built')]
      expect(narrate(events, leadWith([]))).toMatchObject([{ kind: 'assistant_message', bullets: [{}, {}] }])
    },
  )

  it('makes a run of provider lookups one bullet and keeps only the last triage row of a run', () => {
    const events = [
      event(1, 'provider_called'),
      event(2, 'provider_called'),
      event(3, 'plan_built'),
      event(4, 'triage_completed'),
      event(5, 'triage_completed'),
    ]
    expect(narrate(events, leadWith([]))).toMatchObject([
      {
        bullets: [
          { kind: 'lookups', events: [{ id: 1 }, { id: 2 }] },
          { kind: 'event', event: { id: 3 } },
          { kind: 'event', event: { id: 5 } },
        ],
      },
    ])
  })

  it('makes consecutive workflow rows one message that a bubble, a card or another actor breaks', () => {
    const events = [
      event(1, 'plan_built'),
      event(2, 'triage_completed'),
      event(3, 'message_sent', { message: { subject: 'Hi', body: 'Body' } }),
      event(4, 'plan_built'),
      event(5, 'blocker_opened', { item_id: 7 }),
      event(6, 'plan_built'),
      event(7, 'draft_edited', { actor: 'underwriter' }),
      event(8, 'plan_built'),
    ]
    expect(kinds(events, [openItem])).toEqual([
      'assistant_message',
      'bubble',
      'assistant_message',
      'open_card',
      'assistant_message',
      'line',
      'assistant_message',
    ])
  })

  it('keeps what the system did with a reply in the assistant message, under whichever actor wrote it', () => {
    const events = [
      event(1, 'reply_received', { actor: 'inbound', message: { subject: null, body: 'It is 2019.' } }),
      event(2, 'reply_read', { actor: 'inbound' }),
      event(3, 'fact_observed', { actor: 'inbound' }),
      event(4, 'plan_built'),
    ]
    expect(narrate(events, leadWith([]))).toMatchObject([
      { kind: 'bubble' },
      { kind: 'assistant_message', bullets: [{ event: { id: 2 } }, { event: { id: 3 } }, { event: { id: 4 } }] },
    ])
  })

  it('does not break a message with a row it leaves out', () => {
    const events = [event(1, 'plan_built'), event(2, 'plan_built', { actor: 'assistant' }), event(3, 'plan_built')]
    const [block] = narrate(events, leadWith([]))
    expect(block).toMatchObject({ kind: 'assistant_message', bullets: [{ kind: 'event' }, { kind: 'event' }] })
  })

  it.each([
    [3, 3],
    [4, 1],
  ])('shows a run of %i fact rows as %i bullets', (run, bullets) => {
    const events = Array.from({ length: run }, (_, i) => event(i + 1, 'fact_observed'))
    const [block] = narrate(events, leadWith([]))
    expect(block).toMatchObject({ kind: 'assistant_message' })
    expect('bullets' in block && block.bullets).toHaveLength(bullets)
  })

  it('shows a closed item by the approval of its item, else by the ruling on its choice, else as closed', () => {
    const events = [
      event(1, 'blocker_opened', { item_id: 7 }),
      event(2, 'approval_recorded', { actor: 'underwriter', item_id: 7 }),
      event(3, 'blocker_opened', { item_id: 8, choice_ids: ['I13.fire_fail'] }),
      event(4, 'ruling_recorded', { actor: 'underwriter', choice_ids: ['I13.fire_fail'] }),
      event(5, 'blocker_opened', { item_id: 9 }),
    ]
    const blocks = narrate(events, leadWith([]))
    expect(blocks).toMatchObject([
      { kind: 'resolved_card', closing: { id: 2 } },
      { kind: 'resolved_card', closing: { id: 4 } },
      { kind: 'resolved_card', closing: null },
    ])
  })

  it('ignores a ruling that answers another choice and one that came before the card', () => {
    const events = [
      event(1, 'ruling_recorded', { actor: 'underwriter', choice_ids: ['A'] }),
      event(2, 'blocker_opened', { item_id: 8, choice_ids: ['A'] }),
      event(3, 'ruling_recorded', { actor: 'underwriter', choice_ids: ['B'] }),
    ]
    const blocks = narrate(events, leadWith([]))
    expect(blocks).toMatchObject([
      { kind: 'line', event: { id: 1 } },
      { kind: 'resolved_card', closing: null },
      { kind: 'line', event: { id: 3 } },
    ])
  })
})
