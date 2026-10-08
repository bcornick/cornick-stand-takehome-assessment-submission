// ABOUTME: Tests a lead's conversation against fetch stubbed at the boundary: the summary opens it, the open item follows as a card, and the event timeline is folded under a count of its steps.
// ABOUTME: The step count leaves out the assistant's own events, model bookkeeping and a close that a card shows.
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { components } from '@/api/types'
import type { Chat } from '@/surface'
import { formatTime } from '@/format'
import { LeadConversation,shownSteps } from './LeadConversation'
import type { PanelTarget } from '@/surface'
import { narrate } from './narrate'

type Schemas = components['schemas']

const run: Schemas['RunView'] = {
  run_id: 'run-1',
  mode: 'live',
  seed: 42,
  sim_now: '2026-06-29T08:00:00.000000Z',
  first_pass_complete: true,
  example_prompts: [],
  summary: {
    quotes_sent: 0,
    follow_ups_sent: 0,
    declines_approved: 0,
    waiting_on_underwriter: 1,
    waiting_on_producer: 0,
    waiting_on_data: 0,
    delivery_unknown: 0,
  },
}

const lead: Schemas['LeadDetail'] = {
  lead_id: 'LEAD-00000042-008',
  label: '8924 Lakeview Blvd',
  status: 'in_progress',
  summary: 'The quote packet waits on your approval.',
  revision: 3,
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
        intent_id: 'intent-packet',
        observation_id: null,
        choice_ids: [],
        text: 'The quote packet is ready to send.',
      },
      observation: null,
    },
  ],
  readings: {},
  fields: [],
  missing_fields: [],
  decline_reason: null,
  drafts: [],
}

function event(
  id: number,
  type: Schemas['EventRow']['type'],
  actor: Schemas['EventRow']['actor'],
  summary: string,
  item_id: number | null = null,
): Schemas['EventRow'] {
  return {
    id,
    type,
    actor,
    summary,
    item_id,
    choice_ids: [],
    fact_key: null,
    lookup: null,
    message: null,
    mode: 'live',
    sim_ts: '2026-06-29T08:00:00.000000Z',
  }
}

const events: Schemas['EventRow'][] = [
  event(1, 'lead_received', 'inbound', 'Lead received from the producer'),
  event(2, 'plan_built', 'workflow', 'Built the plan'),
  event(3, 'model_called', 'workflow', 'Called the model'),
  event(4, 'triage_completed', 'assistant', 'Assistant triaged the lead'),
  event(5, 'blocker_closed', 'workflow', 'Closed an item', 9),
  event(6, 'blocker_closed', 'workflow', 'Closed a blocker'),
]

function respond(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
}

const requestOut: Schemas['LeadDetail'] = {
  ...lead,
  summary: 'I asked the producer for the 2 missing fields and am waiting for the reply.',
  blockers: [
    {
      item_id: 20,
      kind: 'producer_reply',
      owner: 'producer',
      detail: { ...lead.blockers[0]!.detail, item_kind: null, intent_id: 'intent-ask', text: 'waiting' },
      observation: null,
    },
  ],
  fields: [
    { key: 'coverage_a', label: 'Dwelling coverage', section: 'Primary Coverages', kind: 'integer', options: [] },
    { key: 'q:contact_email', label: 'Contact email', section: 'Contact', kind: 'text', options: [] },
  ],
  drafts: [
    {
      intent_id: 'intent-old',
      payload_hash: 'b'.repeat(64),
      kind: 'routine_request',
      recipient: 'p@example.com',
      subject: 's',
      body: 'b',
      state: 'closed_unsent',
      round: 1,
      asks: ['Year built'],
      sent_at: '2026-06-27T09:00:00.000000Z',
    },
    {
      intent_id: 'intent-ask',
      payload_hash: 'c'.repeat(64),
      kind: 'routine_request',
      recipient: 'p@example.com',
      subject: 's',
      body: 'b',
      state: 'sent',
      round: 2,
      asks: ['Dwelling coverage', 'Contact email'],
      sent_at: '2026-06-28T08:00:00.000000Z',
    },
  ],
}

function renderLead(
  panel: PanelTarget | null = null,
  onOpen: (target: PanelTarget) => void = () => {},
  detail: Schemas['LeadDetail'] = lead,
) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url === `/api/leads/${lead.lead_id}`) return respond(detail)
      if (url === `/api/leads/${lead.lead_id}/events`) return respond({ events })
      return new Response('{}', { status: 404 })
    }),
  )
  const chat: Chat = { turnsOf: () => [], running: false, send: vi.fn<Chat['send']>() }
  render(
    <LeadConversation
      leadId={lead.lead_id}
      run={run}
      proposals={[]}
      chat={chat}
      refresh={0}
      panel={panel}
      onOpen={onOpen}
      onSelect={() => {}}
      onChange={() => {}}
    />,
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('shownSteps', () => {
  it('counts the lines the timeline shows, a folded run as one', () => {
    expect(shownSteps(narrate(events, lead))).toBe(3)
  })
})

describe('LeadConversation', () => {
  it('opens with the summary, then the open card, then the timeline folded under its step count', async () => {
    renderLead()

    const summary = await screen.findByText(lead.summary)
    expect(screen.getAllByText('Assistant').length).toBeGreaterThan(0)
    const card = screen.getByText('The quote packet is ready to send.')
    expect(summary.compareDocumentPosition(card) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()

    const fold = screen.getByText('Show the work (3 steps)').closest('details')!
    expect(fold).not.toHaveAttribute('open')
    await userEvent.click(screen.getByText('Show the work (3 steps)'))
    expect(fold).toHaveAttribute('open')
  })

  it('shows the request that is out: its round, when it went out and how long ago, its asks by label, and a link to the message', async () => {
    const onOpen = vi.fn()
    renderLead(null, onOpen, requestOut)

    const card = await screen.findByRole('region', { name: 'Request to the producer' })
    expect(card).toHaveTextContent('Round 2')
    expect(card).toHaveTextContent(formatTime('2026-06-28T08:00:00.000000Z'))
    expect(card).toHaveTextContent('1 day ago')
    expect(card).toHaveTextContent('Dwelling coverage')
    expect(card).toHaveTextContent('Contact email')
    expect(card).not.toHaveTextContent('year_built')

    await userEvent.click(within(card).getByRole('button', { name: 'View the request' }))
    expect(onOpen).toHaveBeenCalledWith({ kind: 'message', lead_id: lead.lead_id, id: 'intent-ask' })
  })

  it('shows no request card for a lead that is not waiting on the producer', async () => {
    renderLead()
    await screen.findByText(lead.summary)
    expect(screen.queryByRole('region', { name: 'Request to the producer' })).toBeNull()
  })

  it('hides "Full detail" while the panel shows this lead', async () => {
    renderLead({ kind: 'lead', lead_id: lead.lead_id })
    await screen.findByText(lead.summary)
    expect(screen.queryByRole('button', { name: 'Full detail' })).toBeNull()
  })

  it('offers the event timeline under the opening message, opened on the latest event', async () => {
    const onOpen = vi.fn()
    renderLead(null, onOpen)
    await screen.findByText(lead.summary)

    await userEvent.click(screen.getByRole('button', { name: 'View event timeline' }))

    expect(onOpen).toHaveBeenCalledWith({ kind: 'event', lead_id: lead.lead_id, id: events[events.length - 1]!.id })
  })
})
