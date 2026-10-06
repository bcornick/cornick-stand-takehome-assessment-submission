// ABOUTME: Tests the page against fetch stubbed at the boundary: the queue in the order served with its next action, the open items with a link to their lead, the waiting packet with an Approve that posts the item id and the payload hash, and the fixture-reply control in the queue header.
// ABOUTME: The stubbed responses are typed objects of the generated API types, so a shape the backend does not serve fails the type check.
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

const lead: Schemas['LeadDetail'] = {
  lead_id: row.lead_id,
  label: row.label,
  status: 'in_progress',
  revision: 3,
  facts: [
    {
      key: 'street_address',
      value: '8924 Lakeview Blvd',
      source: 'submitted',
      status: 'accepted',
      confirmed: false,
      evidence: {},
      observation_id: 1,
    },
  ],
  plan: {
    effects: [
      {
        effect: { type: 'no_action', rule: 'RC-2' },
        trace: { board_path: ['06:X'], alternatives: [], choice_ids: [] },
        committed: true,
      },
    ],
    declines_on_every_branch: [],
    proposed_decline: false,
    underwriter_decline: null,
    undecided: [],
    open_choices: [],
    catalogue_questions: [],
    not_evaluated: [
      {
        ref: 'electrical',
        text: 'The Electrical page is not evaluated.',
        producer_text: 'Electrical systems were not reviewed for this quote.',
      },
    ],
  },
  blockers: [
    {
      item_id: 17,
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
        text: 'The quote packet is ready to send.',
      },
      observation: null,
    },
  ],
  fields: [],
  drafts: [packet],
}

const items: Schemas['Item'][] = [
  {
    item_id: 17,
    lead_id: row.lead_id,
    kind: 'underwriter_review',
    detail: lead.blockers[0]!.detail,
  },
]

function respond(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
}

// Answers the routes the page calls and records each call as `METHOD path` with its body.
function stubApi() {
  const calls: string[] = []
  const bodies: unknown[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input)
      calls.push(`${init?.method ?? 'GET'} ${path}`)
      if (init?.body !== undefined) bodies.push(JSON.parse(String(init.body)))
      if (path === '/api/run') return respond(run)
      if (path === '/api/leads') return respond(rows)
      if (path === '/api/items') return respond(items)
      if (path === `/api/leads/${lead.lead_id}`) return respond(lead)
      if (path === `/api/leads/${lead.lead_id}/events`) {
        return respond({ lead_id: lead.lead_id, events: [] })
      }
      if (path === '/api/commands') return respond({ accepted: true, event_id: 9, reason: null })
      if (path === '/api/replies/fixtures') return respond({ replies: [] })
      return new Response('{}', { status: 404 })
    }),
  )
  return { calls, bodies }
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('App', () => {
  it('lists the leads in the order served with their next action', async () => {
    stubApi()
    render(<App />)
    await screen.findByRole('button', { name: row.lead_id })
    const rendered = screen
      .getAllByRole('row')
      .filter((tableRow) => within(tableRow).queryByRole('button') !== null)
    expect(rendered.map((tableRow) => within(tableRow).getByRole('button').textContent)).toEqual(
      rows.map((r) => r.lead_id),
    )
    expect(within(rendered[0]!).getByText('Underwriter review')).toBeInTheDocument()
    expect(within(rendered[1]!).getByText('Producer reply')).toBeInTheDocument()
  })

  it('shows the waiting packet and approves it with the item id and the payload hash', async () => {
    const { calls, bodies } = stubApi()
    render(<App />)
    await userEvent.click(await screen.findByRole('button', { name: row.lead_id }))
    const pane = await screen.findByRole('article')
    expect(within(pane).getByText(/Coverage A \(Dwelling\): \$875,000/, { selector: 'pre' })).toBeInTheDocument()

    const approve = within(within(pane).getByRole('form', { name: 'Approve' }))
    await userEvent.type(approve.getByRole('textbox', { name: 'Reason' }), 'matches the plan')
    await userEvent.click(approve.getByRole('button', { name: 'Approve' }))

    expect(calls).toContain('POST /api/commands')
    expect(bodies[0]).toMatchObject({
      type: 'approve',
      payload: { item_id: 17, artifact_hash: packet.payload_hash, reason: 'matches the plan' },
    })
    // The queue and the lead are fetched again after the action.
    await vi.waitFor(() => expect(calls.filter((c) => c === 'GET /api/leads')).toHaveLength(2))
  })

  it('lists the open items and opens the lead of an item', async () => {
    stubApi()
    render(<App />)
    const section = await screen.findByRole('region', { name: 'Open items' })
    expect(within(section).getByText('The quote packet is ready to send.')).toBeInTheDocument()

    await userEvent.click(within(section).getByRole('button', { name: `Open ${row.lead_id}` }))

    const pane = await screen.findByRole('article')
    expect(within(pane).getByRole('heading', { name: row.lead_id })).toBeInTheDocument()
  })

  it('delivers the fixture replies from the queue header, and the detail pane has no such control', async () => {
    const { calls } = stubApi()
    render(<App />)
    await userEvent.click(await screen.findByRole('button', { name: 'Deliver fixture replies' }))
    expect(calls).toContain('POST /api/replies/fixtures')

    await userEvent.click(await screen.findByRole('button', { name: row.lead_id }))
    const pane = await screen.findByRole('article')
    expect(within(pane).queryByRole('button', { name: 'Deliver fixture replies' })).toBeNull()
  })
})
