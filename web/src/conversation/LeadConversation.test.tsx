// ABOUTME: Tests a lead's conversation against fetch stubbed at the boundary: the summary opens it, the open item follows as a card, and the event timeline is folded under a count of its steps.
// ABOUTME: The step count leaves out the assistant's own events, model bookkeeping and a close that a card shows.
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { components } from '@/api/types'
import type { Chat } from '@/surface'
import { LeadConversation, shownSteps } from './LeadConversation'

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
  fields: [],
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

function renderLead() {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url === `/api/leads/${lead.lead_id}`) return respond(lead)
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
      onOpen={() => {}}
      onSelect={() => {}}
      onChange={() => {}}
    />,
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('shownSteps', () => {
  it('counts the events the timeline shows', () => {
    expect(shownSteps(events)).toBe(3)
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
})
