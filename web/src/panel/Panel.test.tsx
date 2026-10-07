// ABOUTME: Tests the drill-down panel against fetch stubbed at the boundary: each kind of target opens its own view, the fact view lists every observation of its key, a neighbour link opens the next event, and Close closes.
// ABOUTME: The lead and its events are typed objects of the generated API types, so a shape the backend does not serve fails the type check.
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { components } from '@/api/types'
import type { PanelTarget } from '@/surface'
import { Panel } from './Panel'

type Schemas = components['schemas']

function event(id: number, fields: Partial<Schemas['EventRow']>): Schemas['EventRow'] {
  return {
    id,
    type: 'lead_received',
    actor: 'workflow',
    sim_ts: '2026-06-29T08:00:00Z',
    summary: `Summary of event ${id}`,
    choice_ids: [],
    fact_key: null,
    item_id: null,
    message: null,
    lookup: null,
    mode: 'live',
    ...fields,
  }
}

const events = [
  event(1, { type: 'fact_observed', fact_key: 'roof_age', summary: 'The submission gave roof_age 12' }),
  event(2, { type: 'reply_received', actor: 'inbound', message: { subject: 'Re: roof', body: 'The roof is slate.' } }),
  event(3, { type: 'fact_observed', fact_key: 'roof_age', summary: 'A reply gave roof_age 15 (pending)' }),
]

const draft: Schemas['DraftView'] = {
  intent_id: 'intent-1',
  payload_hash: 'a'.repeat(64),
  kind: 'routine_request',
  recipient: 'producer@example.com',
  subject: 'Information needed',
  body: 'Please send the roof material.',
  state: 'sent',
  round: 1,
}

const lead: Schemas['LeadDetail'] = {
  lead_id: 'LEAD-1',
  label: '12 Oak St',
  status: 'in_progress',
  summary: 'Triage is running.',  revision: 1,
  facts: [
    {
      key: 'roof_age',
      value: 12,
      source: 'submitted',
      status: 'accepted',
      confirmed: false,
      evidence: {},
      observation_id: 1,
      event_id: 1,
    },
  ],
  pages: [
    {
      key: 'roof_page',
      effects: [
        {
          committed: false,
          effect: { type: 'surcharge', rule: 'R7', percent: 10, deadline: null },
          trace: { alternatives: [], board_path: ['n1', 'n2'], choice_ids: [] },
        },
      ],
      declines_on_every_branch: [],
      waits_on: ['wall_type'],
      not_evaluated: [{ ref: 'N1', text: 'Flood was not evaluated.', producer_text: '' }],
    },
  ],
  plan: null,
  blockers: [],
  fields: [{ key: 'roof_age', label: 'Roof age', kind: 'integer', options: [] }],
  drafts: [draft],
}

function respond(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
}

function stubApi() {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) =>
      String(input).endsWith('/events') ? respond({ lead_id: lead.lead_id, events }) : respond(lead),
    ),
  )
}

function panel(target: PanelTarget, handlers: { onOpen?: (t: PanelTarget) => void; onClose?: () => void } = {}) {
  render(
    <Panel
      target={target}
      refresh={0}
      onOpen={handlers.onOpen ?? (() => {})}
      onClose={handlers.onClose ?? (() => {})}
      onChange={() => {}}
    />,
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('the view of each target', () => {
  it.each<[string, PanelTarget, string]>([
    ['an event', { kind: 'event', lead_id: 'LEAD-1', id: 1 }, 'Fact observed'],
    ['a fact', { kind: 'fact', lead_id: 'LEAD-1', id: 1 }, 'Submitted'],
    ['a message', { kind: 'message', lead_id: 'LEAD-1', id: 'intent-1' }, 'Message (current)'],
    ['a reply', { kind: 'reply', lead_id: 'LEAD-1', id: 2 }, 'The roof is slate.'],
    ['a page', { kind: 'page', lead_id: 'LEAD-1', id: 'roof_page' }, 'roof_page (current)'],
    ['the full lead', { kind: 'lead', lead_id: 'LEAD-1' }, 'Lead actions'],
  ])('opens %s', async (_name, target, expected) => {
    stubApi()
    panel(target)
    expect(await screen.findByText(expected)).toBeInTheDocument()
  })

  it('shows a page with its committed state, board path, waits and notes', async () => {
    stubApi()
    panel({ kind: 'page', lead_id: 'LEAD-1', id: 'roof_page' })
    expect(await screen.findByText('Surcharge (R7): 10% - not committed')).toBeInTheDocument()
    expect(screen.getByText('n1 > n2')).toBeInTheDocument()
    expect(screen.getByText('Waits on wall_type')).toBeInTheDocument()
    expect(screen.getByText('Flood was not evaluated.')).toBeInTheDocument()
  })

  it.each<[string, PanelTarget]>([
    ['an event', { kind: 'event', lead_id: 'LEAD-1', id: 99 }],
    ['a message', { kind: 'message', lead_id: 'LEAD-1', id: 'intent-9' }],
    ['a page', { kind: 'page', lead_id: 'LEAD-1', id: 'none' }],
  ])('says %s the lead does not hold was not found', async (_name, target) => {
    stubApi()
    panel(target)
    expect(await screen.findByText('Not found.')).toBeInTheDocument()
  })
})

describe('the fact view', () => {
  it('lists every observation of the key, the pending one among them', async () => {
    stubApi()
    panel({ kind: 'fact', lead_id: 'LEAD-1', id: 1 })
    const observations = await screen.findByRole('region', { name: 'Observations' })
    expect(screen.getByRole('region', { name: 'Value in use' })).toHaveTextContent('Roof age roof_age')
    expect(observations).toHaveTextContent('The submission gave roof_age 12')
    expect(observations).toHaveTextContent('A reply gave roof_age 15 (pending)')
  })

  it('opens the event that recorded the value in use', async () => {
    stubApi()
    const onOpen = vi.fn()
    panel({ kind: 'fact', lead_id: 'LEAD-1', id: 3 }, { onOpen })
    await userEvent.click(await screen.findByRole('button', { name: /^Recorded / }))
    expect(onOpen).toHaveBeenCalledWith({ kind: 'event', lead_id: 'LEAD-1', id: 1 })
  })
})

describe('the event view', () => {
  it('shows the whole timeline with the cited event expanded, and a click on another row moves the expansion', async () => {
    stubApi()
    const onOpen = vi.fn()
    panel({ kind: 'event', lead_id: 'LEAD-1', id: 2 }, { onOpen })
    const timeline = within(await screen.findByRole('list', { name: 'Timeline' }))
    const rows = timeline.getAllByRole('listitem')
    expect(rows).toHaveLength(events.length)
    expect(rows[1]).toHaveAttribute('aria-current', 'true')
    expect(within(rows[1]).getByText('The roof is slate.')).toBeInTheDocument()
    expect(within(rows[0]).getByText('The submission gave Roof age 12')).toBeInTheDocument()

    await userEvent.click(within(rows[0]).getByRole('button'))
    expect(onOpen).toHaveBeenCalledWith({ kind: 'event', lead_id: 'LEAD-1', id: 1 })
  })
})

describe('the panel', () => {
  it('closes with the Close button', async () => {
    stubApi()
    const onClose = vi.fn()
    panel({ kind: 'lead', lead_id: 'LEAD-1' }, { onClose })
    await userEvent.click(screen.getByRole('button', { name: 'Close' }))
    expect(onClose).toHaveBeenCalledOnce()
  })
})
