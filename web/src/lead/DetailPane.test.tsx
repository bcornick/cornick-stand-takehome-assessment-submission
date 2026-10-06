// ABOUTME: Tests the detail pane's controls against fetch stubbed at the boundary: each action posts the command and payload the architecture names, a refusal reason renders, and a reason or a reply cannot be left empty.
// ABOUTME: The lead is a typed object of the generated API types, so a shape the backend does not serve fails the type check.
import { render, screen, waitFor, within } from '@testing-library/react'
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

const pending: Schemas['FactView'] = {
  key: 'months_unoccupied',
  value: 5,
  source: 'reply',
  status: 'pending_review',
  confirmed: false,
  evidence: {},
  observation_id: 41,
}

function blocker(
  itemId: number,
  kind: Schemas['BlockerView']['kind'],
  detail: Partial<Schemas['BlockerDetail']>,
  observation: Schemas['FactView'] | null = null,
): Schemas['BlockerView'] {
  return {
    item_id: itemId,
    kind,
    owner: 'underwriter',
    detail: { ...noDetail, ...detail },
    observation,
  }
}

const lead: Schemas['LeadDetail'] = {
  lead_id: 'LEAD-1',
  label: '12 Oak St',
  status: 'in_progress',
  revision: 1,
  facts: [
    {
      key: 'coverage_a',
      value: 400000,
      source: 'submitted',
      status: 'accepted',
      confirmed: false,
      evidence: {},
      observation_id: 1,
    },
    {
      key: 'roof_age',
      value: 12,
      source: 'submitted',
      status: 'accepted',
      confirmed: false,
      evidence: {},
      observation_id: 2,
    },
  ],
  plan: {
    effects: [],
    declines_on_every_branch: [],
    proposed_decline: false,
    underwriter_decline: null,
    undecided: [],
    open_choices: [
      {
        choice_id: 'I13.fire_fail',
        options: ['decline', 'legacy_underwriting'],
        prompt: 'The fire simulation failed: decline, or continue?',
        show: ['roof_age', 'wall_type'],
      },
    ],
    catalogue_questions: [],
    not_evaluated: [],
  },
  blockers: [
    blocker(17, 'underwriter_review', { item_kind: 'draft', intent_id: packet.intent_id, text: 'The packet is ready.' }),
    blocker(18, 'underwriter_review', { item_kind: 'observation', observation_id: 41, text: 'A reply gives 5.' }, pending),
    blocker(19, 'underwriter_question', { choice_ids: ['I13.fire_fail'], text: 'The fire simulation failed.' }),
    blocker(20, 'underwriter_review', { item_kind: 'review', cause: 'late_reply', text: 'A late reply.' }),
    blocker(21, 'underwriter_review', { item_kind: 'no_contact_route', text: 'No contact route.' }),
  ],
  drafts: [sentRequest, packet],
}

function respond(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
}

// Answers every route with `answer` and records each call as `METHOD path` with its body.
function stubApi(answer: unknown = { accepted: true, event_id: 9, reason: null }) {
  const posted: { path: string; body: unknown }[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input)
      if (init?.method === 'POST') {
        posted.push({ path, body: JSON.parse(String(init.body)) })
        return respond(answer)
      }
      return respond({ lead_id: lead.lead_id, events: [] })
    }),
  )
  return posted
}

function pane(detail: Schemas['LeadDetail'] = lead) {
  render(<DetailPane lead={detail} refresh={0} onChange={() => {}} />)
}

// The form of the given name inside the item whose text is `itemText`.
function form(itemText: string, name: string) {
  const item = screen.getByText(itemText).closest('li')!
  return within(within(item).getByRole('form', { name }))
}

async function fill(scope: ReturnType<typeof form>, label: string, text: string) {
  const field = scope.getByLabelText(label)
  await userEvent.clear(field)
  await userEvent.type(field, text)
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('the items of a lead', () => {
  it('edits a draft with its new subject and body and a reason', async () => {
    const posted = stubApi()
    pane()
    const edit = form('The packet is ready.', 'Edit')
    expect(edit.getByRole('button', { name: 'Edit' })).toBeDisabled()

    await fill(edit, 'Subject', 'Your quote, checked')
    await fill(edit, 'Body', 'Checked.')
    await fill(edit, 'Reason', 'too stiff')
    await userEvent.click(edit.getByRole('button', { name: 'Edit' }))

    expect(posted).toEqual([
      {
        path: '/api/commands',
        body: {
          type: 'edit_draft',
          payload: {
            intent_id: packet.intent_id,
            subject: 'Your quote, checked',
            body: 'Checked.',
            reason: 'too stiff',
          },
        },
      },
    ])
  })

  it('rejects a draft only with a reason', async () => {
    const posted = stubApi()
    pane()
    const rejectForm = form('The packet is ready.', 'Reject')
    expect(rejectForm.getByRole('button', { name: 'Reject' })).toBeDisabled()

    await fill(rejectForm, 'Reason', 'the roof is wrong')
    await userEvent.click(rejectForm.getByRole('button', { name: 'Reject' }))

    expect(posted[0]).toEqual({
      path: '/api/commands',
      body: { type: 'reject', payload: { item_id: 17, reason: 'the roof is wrong' } },
    })
  })

  it.each([
    ['Approve', { type: 'approve', payload: { item_id: 18, artifact_hash: null, reason: 'clear' } }],
    ['Reject', { type: 'reject', payload: { item_id: 18, reason: 'clear' } }],
  ])('%s a pending value with a reason', async (name, body) => {
    const posted = stubApi()
    pane()
    expect(screen.getByText('Pending value for months_unoccupied: 5')).toBeInTheDocument()

    const scope = form('A reply gives 5.', name)
    await fill(scope, 'Reason', 'clear')
    await userEvent.click(scope.getByRole('button', { name }))

    expect(posted).toEqual([{ path: '/api/commands', body }])
  })

  it('acknowledges a late-reply review but offers no reject, and a missing contact route offers neither', () => {
    stubApi()
    pane()
    const review = screen.getByText('A late reply.').closest('li')!
    expect(within(review).getByRole('form', { name: 'Approve' })).toBeInTheDocument()
    expect(within(review).queryByRole('form', { name: 'Reject' })).toBeNull()
    const route = screen.getByText('No contact route.').closest('li')!
    expect(within(route).queryByRole('form')).toBeNull()
    expect(within(route).getByText(/resolved or the lead is declined/)).toBeInTheDocument()
  })

  it('shows the refusal reason the command returns', async () => {
    stubApi({ accepted: false, event_id: null, reason: 'the cause persists' })
    pane()
    const scope = form('A reply gives 5.', 'Approve')
    await fill(scope, 'Reason', 'clear')
    await userEvent.click(scope.getByRole('button', { name: 'Approve' }))

    expect(await scope.findByRole('alert')).toHaveTextContent('the cause persists')
  })
})

describe('the question card', () => {
  it('shows the choice with the values it needs and no option chosen', () => {
    stubApi()
    pane()
    const card = screen.getByRole('region', { name: 'I13.fire_fail' })
    expect(within(card).getByText('The fire simulation failed: decline, or continue?')).toBeInTheDocument()
    expect(within(card).getByText('roof_age: 12')).toBeInTheDocument()
    expect(within(card).getByText('wall_type: —')).toBeInTheDocument()
    expect(within(card).getAllByRole('button').map((b) => b.textContent)).toEqual([
      'decline',
      'legacy underwriting',
    ])
  })

  it('requires a reason before an option can be chosen, then posts the ruling', async () => {
    const posted = stubApi()
    pane()
    const card = within(screen.getByRole('region', { name: 'I13.fire_fail' }))
    for (const button of card.getAllByRole('button')) expect(button).toBeDisabled()

    await userEvent.type(screen.getByLabelText('Reason for the choice'), 'the checklist is met')
    await userEvent.click(card.getByRole('button', { name: 'legacy underwriting' }))

    expect(posted).toEqual([
      {
        path: '/api/commands',
        body: {
          type: 'record_ruling',
          payload: {
            lead_id: 'LEAD-1',
            choice_id: 'I13.fire_fail',
            option: 'legacy_underwriting',
            reason: 'the checklist is met',
          },
        },
      },
    ])
    await waitFor(() => expect(screen.getByLabelText('Reason for the choice')).toHaveValue(''))
  })
})

describe('the actions on the lead', () => {
  it('resolves a fact as a number when the lead holds that fact as a number', async () => {
    const posted = stubApi()
    pane()
    const scope = within(screen.getByRole('form', { name: 'Resolve fact' }))
    expect(scope.getByRole('button', { name: 'Resolve fact' })).toBeDisabled()

    await fill(scope, 'Field', 'coverage_a')
    await fill(scope, 'Value', '500000')
    await fill(scope, 'Reason', 'by phone')
    await userEvent.click(scope.getByRole('button', { name: 'Resolve fact' }))

    expect(posted).toEqual([
      {
        path: '/api/commands',
        body: {
          type: 'resolve_fact',
          payload: { lead_id: 'LEAD-1', key: 'coverage_a', value: 500000, reason: 'by phone' },
        },
      },
    ])
  })

  it('declines the lead with a reason', async () => {
    const posted = stubApi()
    pane()
    const scope = within(screen.getByRole('form', { name: 'Decline lead' }))
    await fill(scope, 'Reason', 'outside appetite')
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
    stubApi()
    pane({ ...lead, status: 'declined', drafts: [packet] })
    expect(screen.queryByRole('form', { name: 'Paste a reply' })).toBeNull()
    expect(screen.queryByRole('form', { name: 'Decline lead' })).toBeNull()
    expect(screen.queryByRole('form', { name: 'Resolve fact' })).toBeNull()
  })
})
