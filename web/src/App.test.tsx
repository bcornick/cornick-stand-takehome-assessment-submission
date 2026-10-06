// ABOUTME: Tests the surface against fetch stubbed at the boundary: lead 008 goes from "Load today's leads" to an approved packet inside its conversation, the queue conversation holds the cards of leads 000 and 003, and a citation chip opens the panel on what it cites.
// ABOUTME: The stubbed responses are typed objects of the generated API types, so a shape the backend does not serve fails the type check; the stub keeps the run's state, so a control changes what the next fetch returns.
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { components } from '@/api/types'
import App from './App'

type Schemas = components['schemas']

const run: Schemas['RunView'] = {
  run_id: 'run-1',
  mode: 'replay',
  seed: 42,
  sim_now: '2026-06-29T08:00:00.000000Z',
  first_pass_complete: true,
  example_prompts: [],
  summary: {
    quotes_sent: 0,
    follow_ups_sent: 1,
    declines_approved: 0,
    waiting_on_underwriter: 1,
    waiting_on_producer: 1,
    waiting_on_data: 0,
    delivery_unknown: 0,
  },
}

const row: Schemas['QueueRow'] = {
  lead_id: 'LEAD-00000042-008',
  label: '8924 Lakeview Blvd',
  status: 'in_progress',
  primary_next_action: 'underwriter_review',
  waits_on: 'underwriter',
  age_business_days: 0.5,
  service_level_breached: false,
  effective_date: '2026-07-23',
  ask_count: 2,
  group: 'blocked_on_underwriter',
}
const rows: Schemas['QueueRow'][] = [
  row,
  {
    ...row,
    lead_id: 'LEAD-00000042-001',
    label: '12 Oak St',
    primary_next_action: 'producer_reply',
    waits_on: 'producer',
    group: 'waiting_on_data_or_producer',
  },
]

const packet: Schemas['DraftView'] = {
  intent_id: 'intent-packet',
  payload_hash: 'a'.repeat(64),
  kind: 'quote_packet',
  recipient: 'producer@example.com',
  subject: 'Your quote: 8924 Lakeview Blvd',
  body: 'Thank you for your submission.\n\nCoverages as submitted\n- Coverage A (Dwelling): $875,000',
  state: 'draft',
  round: 2,
}

const LEAD_000 = 'LEAD-00000042-000'
const LEAD_003 = 'LEAD-00000042-003'

function detail(text: string, more: Partial<Schemas['BlockerDetail']>): Schemas['BlockerDetail'] {
  return {
    item_kind: 'draft',
    cause: null,
    cause_persists: false,
    resume_trigger: 'the underwriter decides',
    intent_id: null,
    observation_id: null,
    choice_ids: [],
    text,
    ...more,
  }
}

const packetDetail = detail('The quote packet is ready to send.', { intent_id: packet.intent_id })

const plan: Schemas['ActionPlan'] = {
  effects: [],
  declines_on_every_branch: [],
  proposed_decline: false,
  underwriter_decline: null,
  undecided: [],
  open_choices: [],
  catalogue_questions: [],
  not_evaluated: [],
}

// Lead 008 as the first pass leaves it: a request sent, nothing for the underwriter.
const lead: Schemas['LeadDetail'] = {
  lead_id: row.lead_id,
  label: row.label,
  status: 'in_progress',
  summary: 'Triage is running.',  revision: 3,
  facts: [
    {
      key: 'roof_year',
      value: 2019,
      source: 'submitted',
      status: 'accepted',
      confirmed: false,
      evidence: {},
      observation_id: 1,
      event_id: 6,
    },
  ],
  pages: [],
  plan,
  blockers: [],
  fields: [{ key: 'roof_year', label: 'Roof year', kind: 'integer', options: [] }],
  drafts: [],
}

// The same lead once the producer's reply has been read: the packet waits on the underwriter.
const leadWithPacket: Schemas['LeadDetail'] = {
  ...lead,
  blockers: [{ item_id: 17, kind: 'underwriter_review', owner: 'underwriter', detail: packetDetail, observation: null }],
  drafts: [packet],
}

const declineNotice: Schemas['DraftView'] = {
  ...packet,
  intent_id: 'intent-decline',
  kind: 'decline_notice',
  subject: 'Your submission',
  body: 'We are unable to offer a quote.',
  round: 1,
}
const declineDetail = detail('The lead is a proposed decline.', { intent_id: declineNotice.intent_id })
const fireDetail = detail('The fire simulation failed.', { item_kind: null, choice_ids: ['I13.fire_fail'] })

const otherLeads: Record<string, Schemas['LeadDetail']> = {
  [LEAD_000]: {
    ...lead,
    lead_id: LEAD_000,
    label: '1 Ash Rd',
    blockers: [{ item_id: 3, kind: 'underwriter_review', owner: 'underwriter', detail: declineDetail, observation: null }],
    drafts: [declineNotice],
  },
  [LEAD_003]: {
    ...lead,
    lead_id: LEAD_003,
    label: '3 Elm Ct',
    plan: {
      ...plan,
      open_choices: [
        {
          choice_id: 'I13.fire_fail',
          options: ['legacy_underwriting', 'decline'],
          prompt: 'The fire simulation failed. How should this lead be underwritten?',
          show: [],
        },
      ],
    },
    blockers: [{ item_id: 5, kind: 'underwriter_question', owner: 'underwriter', detail: fireDetail, observation: null }],
  },
}

const items: Schemas['Item'][] = [
  { item_id: 3, lead_id: LEAD_000, kind: 'underwriter_review', detail: declineDetail },
  { item_id: 5, lead_id: LEAD_003, kind: 'underwriter_question', detail: fireDetail },
]

function event(id: number, type: Schemas['EventRow']['type'], summary: string, more: Partial<Schemas['EventRow']> = {}): Schemas['EventRow'] {
  return {
    id,
    type,
    mode: 'replay',
    actor: 'workflow',
    sim_ts: '2026-06-29T08:00:00+00:00',
    summary,
    item_id: null,
    choice_ids: [],
    fact_key: null,
    message: null,
    lookup: null,
    ...more,
  }
}

const firstPassEvents = [
  event(1, 'triage_completed', 'Triaged the fields: 14 missing'),
  event(2, 'provider_called', 'Fetched the replacement cost: 928992', { lookup: { status: 'found', missing_inputs: [] } }),
  event(6, 'fact_observed', 'Recorded roof_year as 2019 (submitted)', { fact_key: 'roof_year' }),
  event(3, 'message_sent', 'Sent the message to the producer', {
    message: { subject: 'Information needed for your quote', body: 'What year was the roof replaced?' },
  }),
]
const replyEvents = [
  event(4, 'reply_received', 'The producer replied', {
    actor: 'inbound',
    message: { subject: null, body: 'The roof was replaced in 2019.' },
  }),
  event(5, 'blocker_opened', 'Waiting on the underwriter. The quote packet is ready to send.', { item_id: 17 }),
]

function respond(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
}

// Answers the routes the page calls from the run's state and records each call as `METHOD path` with its body.
// The day starts with no run unless `loaded`; loading the leads and delivering the replies move the state on.
function stubApi(loaded: boolean) {
  const calls: string[] = []
  const bodies: unknown[] = []
  const state = { loaded, replied: false }
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input)
      calls.push(`${init?.method ?? 'GET'} ${path}`)
      if (init?.body !== undefined) bodies.push(JSON.parse(String(init.body)))
      if (path === '/api/run/start?wait=true') state.loaded = true
      if (path === '/api/replies/fixtures') {
        state.replied = true
        return respond({ replies: [] })
      }
      if (path.startsWith('/api/run')) return respond(state.loaded ? run : { ...run, run_id: null })
      if (path === '/api/leads') return respond(state.loaded ? rows : [])
      if (path === '/api/items') return respond(state.loaded ? items : [])
      if (path === '/api/proposals') return respond([])
      if (path === `/api/leads/${lead.lead_id}`) return respond(state.replied ? leadWithPacket : lead)
      if (path === `/api/leads/${lead.lead_id}/events`) {
        const events = state.replied ? [...firstPassEvents, ...replyEvents] : firstPassEvents
        return respond({ lead_id: lead.lead_id, events })
      }
      const [otherId, events] = path.slice('/api/leads/'.length).split('/')
      const other = otherLeads[otherId ?? '']
      if (other !== undefined) return respond(events === undefined ? other : { lead_id: otherId, events: [] })
      if (path === '/api/commands') return respond({ accepted: true, event_id: 9, reason: null })
      return new Response('{}', { status: 404 })
    }),
  )
  return { calls, bodies }
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('App', () => {
  it('takes lead 008 from loading the leads to an approved packet inside its conversation', async () => {
    const { calls, bodies } = stubApi(false)
    render(<App />)
    const demo = within(await screen.findByRole('complementary', { name: 'Demo controls' }))
    const leads = within(screen.getByRole('navigation', { name: 'Leads' }))
    expect(leads.queryByRole('button', { name: /Lead 008/ })).toBeNull()

    await userEvent.click(demo.getByRole('button', { name: 'Demo controls' }))
    await userEvent.click(demo.getByRole('button', { name: "Load today's leads" }))
    await userEvent.click(await leads.findByRole('button', { name: /Lead 008/ }))

    const conversation = within(await screen.findByRole('region', { name: 'Conversation' }))
    expect(await conversation.findByText('Triaged the fields: 14 missing')).toBeInTheDocument()
    expect(conversation.getByText('Information needed for your quote')).toBeInTheDocument()
    expect(conversation.queryByRole('form', { name: 'Approve' })).toBeNull()

    await userEvent.click(demo.getByRole('button', { name: "Deliver the producers' replies" }))

    expect(await conversation.findByText('The roof was replaced in 2019.')).toBeInTheDocument()
    await userEvent.click(conversation.getByRole('button', { name: 'Approve' }))
    const confirm = within(conversation.getByRole('form', { name: 'Confirm the choice' }))
    await userEvent.type(confirm.getByRole('textbox'), 'matches the plan')
    await userEvent.click(confirm.getByRole('button', { name: 'Approve' }))

    expect(calls).toContain('POST /api/run/start?wait=true')
    expect(calls).toContain('POST /api/replies/fixtures')
    expect(bodies.at(-1)).toMatchObject({
      type: 'approve',
      payload: { item_id: 17, artifact_hash: packet.payload_hash, reason: 'matches the plan' },
    })
  })

  it('holds the cards of leads 000 and 003 in the queue conversation, and a card opens its lead', async () => {
    stubApi(true)
    render(<App />)
    const conversation = within(await screen.findByRole('region', { name: 'Conversation' }))

    expect(await conversation.findByRole('button', { name: 'Withdraw decline and send the asks' })).toBeInTheDocument()
    expect(await conversation.findByRole('button', { name: 'Legacy underwriting' })).toBeInTheDocument()
    expect(conversation.getByRole('button', { name: 'Decline' })).toBeInTheDocument()

    await userEvent.click(conversation.getByRole('button', { name: /Lead 003/ }))

    expect(await screen.findByRole('heading', { name: /Lead 003/ })).toBeInTheDocument()
  })

  it('opens the panel on the fact a chip cites, and closes it', async () => {
    stubApi(true)
    render(<App />)
    const leads = within(await screen.findByRole('navigation', { name: 'Leads' }))
    await userEvent.click(await leads.findByRole('button', { name: /Lead 008/ }))
    const conversation = within(await screen.findByRole('region', { name: 'Conversation' }))
    expect(screen.queryByRole('complementary', { name: 'Detail' })).toBeNull()

    await userEvent.click(await conversation.findByRole('button', { name: 'Open fact roof_year' }))

    const panel = within(await screen.findByRole('complementary', { name: 'Detail' }))
    expect(await panel.findByText('Roof year')).toBeInTheDocument()
    expect(panel.getByText('2019')).toBeInTheDocument()

    await userEvent.click(panel.getByRole('button', { name: 'Close' }))
    expect(screen.queryByRole('complementary', { name: 'Detail' })).toBeNull()
  })
})
