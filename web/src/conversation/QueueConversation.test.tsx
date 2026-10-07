// ABOUTME: Tests the queue conversation against fetch stubbed at the boundary: an open item as a card with a link to its lead and its action, the empty line with no run, and the example prompts.
// ABOUTME: The stubbed responses are typed objects of the generated API types, so a shape the backend does not serve fails the type check.
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { components } from '@/api/types'
import { QUEUE, type Chat } from '@/surface'
import { QueueConversation } from './QueueConversation'

type Schemas = components['schemas']

const run: Schemas['RunView'] = {
  run_id: 'run-1',
  mode: 'live',
  seed: 42,
  sim_now: '2026-06-29T08:00:00.000000Z',
  first_pass_complete: true,
  example_prompts: ['Which leads are blocked on me?'],
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

const packet: Schemas['DraftView'] = {
  intent_id: 'intent-packet',
  payload_hash: 'a'.repeat(64),
  kind: 'quote_packet',
  recipient: 'producer@example.com',
  subject: 'Your quote: 8924 Lakeview Blvd',
  body: 'Thank you for your submission.',
  state: 'draft',
  round: 2,
}

const lead: Schemas['LeadDetail'] = {
  lead_id: 'LEAD-00000042-008',
  label: '8924 Lakeview Blvd',
  status: 'in_progress',
  summary: 'Triage is running.',  revision: 3,
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
  { item_id: 17, lead_id: lead.lead_id, kind: 'underwriter_review', detail: lead.blockers[0]!.detail },
]

function respond(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
}

function stubLead(served: Schemas['LeadDetail']) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) =>
      String(input) === `/api/leads/${served.lead_id}` ? respond(served) : new Response('{}', { status: 404 }),
    ),
  )
}

function chatWith(turns: number) {
  return {
    turnsOf: () => Array.from({ length: turns }, () => ({ message: 'asked', steps: [], closing: null })),
    running: false,
    send: vi.fn<Chat['send']>(),
  }
}

function renderQueue(overrides: { run?: Schemas['RunView']; chat?: Chat; onSelect?: (id: string) => void } = {}) {
  const chat = overrides.chat ?? chatWith(0)
  render(
    <QueueConversation
      items={items}
      run={overrides.run ?? run}
      proposals={[]}
      chat={chat}
      refresh={0}
      panel={null}
      onOpen={() => {}}
      onSelect={overrides.onSelect ?? (() => {})}
      onChange={() => {}}
    />,
  )
  return chat
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('QueueConversation', () => {
  it('shows an open item as a card with a link to its lead and its Approve choice', async () => {
    stubLead(lead)
    const onSelect = vi.fn()
    renderQueue({ onSelect })

    expect(screen.getByText('The quote packet is ready to send.')).toBeInTheDocument()
    expect(await screen.findByRole('button', { name: 'Approve' })).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Lead 008 · 8924 Lakeview Blvd' }))
    expect(onSelect).toHaveBeenCalledWith(lead.lead_id)
  })

  it('opens with the greeting under the Assistant label, not the run counts', () => {
    stubLead(lead)
    renderQueue()

    expect(screen.getByText('Assistant')).toBeInTheDocument()
    expect(screen.getByText('1 lead needs you. 1 is waiting on producers.')).toBeInTheDocument()
    expect(screen.queryByText(/follow-ups sent/)).toBeNull()
  })

  it('shows nothing for an item its lead does not hold', async () => {
    stubLead({ ...lead, blockers: [] })
    renderQueue()

    await vi.waitFor(() => expect(screen.queryByText('The quote packet is ready to send.')).toBeNull())
    expect(screen.queryByRole('button', { name: /Lead 008/ })).toBeNull()
  })

  it('shows only the empty line when no run is loaded', () => {
    stubLead(lead)
    renderQueue({ run: { ...run, run_id: null } })

    expect(
      screen.getByText("No leads are loaded. Use Demo controls, bottom right, to load today's leads."),
    ).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Lead 008/ })).toBeNull()
    expect(screen.queryByRole('button', { name: run.example_prompts[0]! })).toBeNull()
  })

  it('sends an example prompt, shown beside the composer, to the queue conversation', async () => {
    stubLead(lead)
    const chat = renderQueue()

    const prompt = screen.getByRole('button', { name: run.example_prompts[0]! })
    const bottomBar = screen.getByRole('textbox').closest('.border-t')
    expect(bottomBar).toContainElement(prompt)

    await userEvent.click(screen.getByRole('button', { name: run.example_prompts[0]! }))
    expect(chat.send).toHaveBeenCalledWith(QUEUE, run.example_prompts[0])
  })

  it('offers the example prompts in replay too, since they are recorded', async () => {
    stubLead(lead)
    const chat = renderQueue({ run: { ...run, mode: 'replay' } })

    await userEvent.click(screen.getByRole('button', { name: run.example_prompts[0]! }))
    expect(chat.send).toHaveBeenCalledWith(QUEUE, run.example_prompts[0])
  })

  it('offers no example prompts once something has been asked', () => {
    stubLead(lead)
    renderQueue({ chat: chatWith(1) })
    expect(screen.queryByRole('button', { name: run.example_prompts[0]! })).toBeNull()
  })
})
