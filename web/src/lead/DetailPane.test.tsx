// ABOUTME: Tests the full lead view against fetch stubbed at the boundary: what the lead waits on is read-only, and each action on the lead posts the command and payload the architecture names.
// ABOUTME: The lead is a typed object of the generated API types, so a shape the backend does not serve fails the type check.
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { components } from '@/api/types'
import { DetailPane } from './DetailPane'

type Schemas = components['schemas']

const sentRequest: Schemas['DraftView'] = {
  intent_id: 'intent-request',
  payload_hash: 'b'.repeat(64),
  kind: 'routine_request',
  recipient: 'producer@example.com',
  subject: 'Information needed',
  body: 'Please send the roof material.',
  state: 'sent',
  round: 1,
  asks: [],
  sent_at: null,
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

const packetBlocker: Schemas['BlockerView'] = {
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
  plan: null,
  blockers: [packetBlocker],
  readings: {},
  fields: [
    { key: 'coverage_a', label: 'Coverage A', section: 'Primary Coverages', kind: 'integer', options: [] },
    { key: 'zip_code', label: 'Zip code', section: 'Location', kind: 'text', options: [] },
    { key: 'fire_alarm', label: 'Fire alarm', section: 'Protection', kind: 'toggle', options: [] },
  ],
  missing_fields: [],
  drafts: [sentRequest, packet],
}

function respond(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
}

// Answers every command with `answer` and records each call as `path` with its body.
function stubApi(answer: unknown = { accepted: true, event_id: 9, reason: null }) {
  const posted: { path: string; body: unknown }[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      posted.push({ path: String(input), body: JSON.parse(String(init?.body)) })
      return respond(answer)
    }),
  )
  return posted
}

function pane(detail: Schemas['LeadDetail'] = lead) {
  render(<DetailPane lead={detail} onChange={() => {}} />)
}

async function fill(scope: ReturnType<typeof within>, label: string, text: string) {
  const field = scope.getByLabelText(label)
  await userEvent.clear(field)
  await userEvent.type(field, text)
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('what the lead waits on', () => {
  it('names each open item and offers no action on it', () => {
    pane()
    const waiting = within(screen.getByRole('region', { name: 'Waiting on' }))
    expect(waiting.getByText('The packet is ready.')).toBeInTheDocument()
    expect(waiting.queryByRole('form')).toBeNull()
  })
})

describe('the header', () => {
  it('names the lead without the run’s seed', () => {
    pane({ ...lead, lead_id: 'LEAD-00000042-003' })
    expect(screen.getByRole('heading', { level: 2, name: 'LEAD-003' })).toBeInTheDocument()
  })
})

function fact(key: string, value: unknown, source: Schemas['FactView']['source'] = 'submitted'): Schemas['FactView'] {
  return {
    key,
    value: value as Schemas['FactView']['value'],
    source,
    status: 'accepted',
    confirmed: false,
    evidence: {},
    observation_id: 1,
    event_id: 1,
  }
}

describe('the facts', () => {
  it('names a fact by its field label', () => {
    pane({ ...lead, facts: [fact('coverage_a', 500000)] })
    const table = within(screen.getByRole('table', { name: 'Facts' }))
    expect(table.getByText('Coverage A')).toBeInTheDocument()
    expect(table.queryByText('coverage_a')).toBeNull()
  })

  it('groups the facts under the registry’s sections, each in registry order, with a flag in words', () => {
    pane({ ...lead, facts: [fact('fire_alarm', true), fact('zip_code', '34102'), fact('coverage_a', 500000)] })
    const table = within(screen.getByRole('table', { name: 'Facts' }))
    expect(table.getAllByRole('row').map((row) => row.textContent)).toEqual([
      'FieldValueSource',
      'Primary Coverages',
      'Coverage A500000',
      'Location',
      'Zip code34102',
      'Protection',
      'Fire alarmYes',
    ])
  })

  it('shows a source badge only where the source is not Submitted', () => {
    pane({ ...lead, facts: [fact('coverage_a', 500000), fact('zip_code', '34102', 'fetched')] })
    const table = within(screen.getByRole('table', { name: 'Facts' }))
    expect(table.getByText('Fetched')).toBeInTheDocument()
    expect(table.queryByText('Submitted')).toBeNull()
  })

  it('reads a date field as a date', () => {
    const fields = [{ key: 'roof_year', label: 'Roof year', section: 'Construction', kind: 'date', options: [] }]
    pane({ ...lead, fields, facts: [fact('roof_year', '2008-07-15')] })
    expect(within(screen.getByRole('table', { name: 'Facts' })).getByText('Jul 15, 2008')).toBeInTheDocument()
  })

  it('lists the fields the lead is missing by label above the facts, grouped by how each is resolved', () => {
    const missing_fields = [
      { key: 'zip_code', resolution: 'ask' as const },
      { key: 'fire_alarm', resolution: 'fetch' as const },
      { key: 'coverage_a', resolution: 'ask_follow_on' as const },
    ]
    pane({ ...lead, facts: [], missing_fields })
    const missing = within(screen.getByRole('region', { name: 'Missing' }))
    const asked = within(missing.getByRole('list', { name: 'Asked of the producer' }))
    expect(asked.getAllByRole('listitem').map((item) => item.textContent)).toEqual(['Zip code', 'Coverage A'])
    const looked = within(missing.getByRole('list', { name: 'Looked up by the system' }))
    expect(looked.getAllByRole('listitem').map((item) => item.textContent)).toEqual(['Fire alarm'])
  })

  it('lists no missing fields when none are missing', () => {
    pane({ ...lead, facts: [fact('coverage_a', 500000)] })
    expect(screen.queryByRole('region', { name: 'Missing' })).toBeNull()
  })
})

describe('the actions on the lead', () => {
  it('resolves a fact from a choice of the lead’s registry fields, as a number for an integer', async () => {
    const posted = stubApi()
    pane()
    const scope = within(screen.getByRole('form', { name: 'Resolve fact' }))
    expect(scope.getByRole('button', { name: 'Resolve fact' })).toBeDisabled()
    expect(
      scope.getAllByRole('option').map((option) => option.textContent),
    ).toEqual(['', 'Coverage A (coverage_a)', 'Zip code (zip_code)', 'Fire alarm (fire_alarm)'])

    await userEvent.selectOptions(scope.getByLabelText('Field'), 'coverage_a')
    await fill(scope, 'Value', '500000')
    await userEvent.click(scope.getByRole('button', { name: 'Resolve fact' }))

    expect(posted).toEqual([
      {
        path: '/api/commands',
        body: {
          type: 'resolve_fact',
          payload: { lead_id: 'LEAD-1', key: 'coverage_a', value: 500000, reason: '' },
        },
      },
    ])
  })

  it('sends a text field as text, so a zip code keeps its digits, and a toggle as a flag', async () => {
    const posted = stubApi()
    pane()
    const scope = within(screen.getByRole('form', { name: 'Resolve fact' }))

    await userEvent.selectOptions(scope.getByLabelText('Field'), 'zip_code')
    await fill(scope, 'Value', '34102')
    await userEvent.click(scope.getByRole('button', { name: 'Resolve fact' }))
    await userEvent.selectOptions(scope.getByLabelText('Field'), 'fire_alarm')
    await fill(scope, 'Value', 'Yes')
    await fill(scope, 'Notes', 'by phone')
    await userEvent.click(scope.getByRole('button', { name: 'Resolve fact' }))

    expect(posted.map((call) => (call.body as { payload: { key: string; value: unknown } }).payload)).toEqual([
      { lead_id: 'LEAD-1', key: 'zip_code', value: '34102', reason: '' },
      { lead_id: 'LEAD-1', key: 'fire_alarm', value: true, reason: 'by phone' },
    ])
  })

  it('declines the lead with a reason', async () => {
    const posted = stubApi()
    pane()
    const scope = within(screen.getByRole('form', { name: 'Decline lead' }))
    expect(scope.getByRole('button', { name: 'Decline lead' })).toBeDisabled()
    await fill(scope, 'Reason for the decline, kept on file', 'outside appetite')
    await userEvent.click(scope.getByRole('button', { name: 'Decline lead' }))

    expect(posted[0]).toEqual({
      path: '/api/commands',
      body: { type: 'decline_lead', payload: { lead_id: 'LEAD-1', reason: 'outside appetite' } },
    })
  })

  it('pastes a reply against the latest sent request and shows the refusal', async () => {
    const posted = stubApi({ accepted: false, event_id: null, reason: 'already delivered', lead_id: 'LEAD-1' })
    pane()
    const scope = within(screen.getByRole('form', { name: 'Paste a reply' }))
    await fill(scope, 'The producer’s reply', 'The roof is slate.')
    await userEvent.click(scope.getByRole('button', { name: 'Paste a reply' }))

    expect(posted).toEqual([
      {
        path: '/api/replies',
        body: { lead_id: 'LEAD-1', intent_id: 'intent-request', body: 'The roof is slate.' },
      },
    ])
    expect(await scope.findByRole('alert')).toHaveTextContent('already delivered')
  })

  it('offers no paste box without a sent request and no decline once the lead is declined', () => {
    pane({ ...lead, status: 'declined', drafts: [packet] })
    expect(screen.queryByRole('form', { name: 'Paste a reply' })).toBeNull()
    expect(screen.queryByRole('form', { name: 'Decline lead' })).toBeNull()
    expect(screen.queryByRole('form', { name: 'Resolve fact' })).toBeNull()
  })
})
