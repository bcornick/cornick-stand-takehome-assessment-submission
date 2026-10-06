// ABOUTME: Tests the actions of one open item against fetch stubbed at the boundary: each action posts the command and payload the architecture names, a refusal reason renders, and a reason cannot be left empty.
// ABOUTME: The lead is a typed object of the generated API types, so a shape the backend does not serve fails the type check.
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { components } from '@/api/types'
import { OpenItem } from './ItemActions'

type Schemas = components['schemas']

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
const decline: Schemas['DraftView'] = {
  ...packet,
  intent_id: 'intent-decline',
  payload_hash: 'c'.repeat(64),
  kind: 'decline_notice',
  subject: 'Your application',
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
  event_id: 41,
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

const packetItem = blocker(17, 'underwriter_review', {
  item_kind: 'draft',
  intent_id: packet.intent_id,
  text: 'The packet is ready.',
})
const pendingItem = blocker(
  18,
  'underwriter_review',
  { item_kind: 'observation', observation_id: 41, text: 'A reply gives 5.' },
  pending,
)
const questionItem = blocker(19, 'underwriter_question', {
  choice_ids: ['I13.fire_fail'],
  text: 'The fire simulation failed: decline, or continue?',
})
const lateReplyItem = blocker(20, 'underwriter_review', {
  item_kind: 'review',
  cause: 'late_reply',
  text: 'A late reply.',
})
const noRouteItem = blocker(21, 'underwriter_review', {
  item_kind: 'no_contact_route',
  resume_trigger: 'a contact email is resolved',
  text: 'No contact route.',
})
const producerWait: Schemas['BlockerView'] = {
  ...blocker(22, 'producer_reply', {
    resume_trigger: 'the producer replies',
    text: 'Waiting for the producer’s reply to round 1.',
  }),
  owner: 'producer',
}

const lead: Schemas['LeadDetail'] = {
  lead_id: 'LEAD-1',
  label: '12 Oak St',
  status: 'in_progress',
  summary: 'Triage is running.',  revision: 1,
  facts: [
    {
      key: 'months_unoccupied',
      value: 0,
      source: 'submitted',
      status: 'accepted',
      confirmed: false,
      evidence: {},
      observation_id: 3,
      event_id: 3,
    },
    {
      key: 'roof_age',
      value: 12,
      source: 'submitted',
      status: 'accepted',
      confirmed: false,
      evidence: {},
      observation_id: 2,
      event_id: 2,
    },
  ],
  pages: [],
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
  blockers: [],
  fields: [
    { key: 'months_unoccupied', label: 'Months unoccupied', kind: 'number', options: [] },
    { key: 'roof_age', label: 'Roof age', kind: 'number', options: [] },
    { key: 'wall_type', label: 'Wall type', kind: 'text', options: [] },
  ],
  drafts: [packet],
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

function item(blockerView: Schemas['BlockerView'], detail: Schemas['LeadDetail'] = lead) {
  render(<OpenItem lead={detail} blocker={blockerView} onChange={() => {}} />)
}

// The reason form that opens under the buttons once a choice is made.
function reasonForm() {
  return within(screen.getByRole('form', { name: 'Confirm the choice' }))
}

async function choose(name: string, reason: string, confirm = name) {
  await userEvent.click(screen.getByRole('button', { name }))
  await userEvent.type(reasonForm().getByLabelText('Reason'), reason)
  await userEvent.click(reasonForm().getByRole('button', { name: confirm }))
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('a draft card', () => {
  it('shows one reason field only after Approve is chosen, then approves against the hash shown', async () => {
    const posted = stubApi()
    item(packetItem)
    expect(screen.getByRole('button', { name: 'Approve' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Reject' })).toBeEnabled()
    expect(screen.queryByLabelText('Reason')).toBeNull()

    await userEvent.click(screen.getByRole('button', { name: 'Approve' }))
    expect(screen.getAllByLabelText('Reason')).toHaveLength(1)
    expect(reasonForm().getByRole('button', { name: 'Approve' })).toBeDisabled()

    await userEvent.type(reasonForm().getByLabelText('Reason'), 'matches the plan')
    await userEvent.click(reasonForm().getByRole('button', { name: 'Approve' }))

    expect(posted).toEqual([
      {
        path: '/api/commands',
        body: {
          type: 'approve',
          payload: { item_id: 17, artifact_hash: packet.payload_hash, reason: 'matches the plan' },
        },
      },
    ])
  })

  it('rejects a draft only with a reason', async () => {
    const posted = stubApi()
    item(packetItem)
    await userEvent.click(screen.getByRole('button', { name: 'Reject' }))
    expect(reasonForm().getByRole('button', { name: 'Reject' })).toBeDisabled()

    await userEvent.type(reasonForm().getByLabelText('Reason'), 'the roof is wrong')
    await userEvent.click(reasonForm().getByRole('button', { name: 'Reject' }))

    expect(posted[0]).toEqual({
      path: '/api/commands',
      body: { type: 'reject', payload: { item_id: 17, reason: 'the roof is wrong' } },
    })
  })

  it('hides the reason field again on Cancel', async () => {
    const posted = stubApi()
    item(packetItem)
    await userEvent.click(screen.getByRole('button', { name: 'Reject' }))
    await userEvent.click(reasonForm().getByRole('button', { name: 'Cancel' }))

    expect(screen.queryByLabelText('Reason')).toBeNull()
    expect(posted).toEqual([])
  })

  it('rejects a decline notice as withdrawing the decline and sending the asks, and says so once chosen', async () => {
    const posted = stubApi()
    item(
      blocker(30, 'underwriter_review', { item_kind: 'draft', intent_id: decline.intent_id, text: 'Review the notice.' }),
      { ...lead, drafts: [decline] },
    )
    expect(screen.queryByRole('button', { name: 'Reject' })).toBeNull()
    expect(screen.getByText('Preview the notice')).toBeInTheDocument()
    expect(screen.queryByText(/sends the requests for the facts still missing/)).toBeNull()

    await userEvent.click(screen.getByRole('button', { name: 'Withdraw decline and send the asks' }))
    expect(screen.getByText(/sends the requests for the facts still missing/)).toBeInTheDocument()
    await userEvent.type(reasonForm().getByLabelText('Reason'), 'the roof is fine')
    await userEvent.click(reasonForm().getByRole('button', { name: 'Withdraw decline and send the asks' }))

    expect(posted[0].body).toEqual({ type: 'reject', payload: { item_id: 30, reason: 'the roof is fine' } })
  })

  it('folds the subject and body in a preview, and Edit inside it posts the new text with a reason', async () => {
    const posted = stubApi()
    item(packetItem)
    const preview = screen.getByText('Preview the packet').closest('details')!
    expect(preview).not.toHaveAttribute('open')
    expect(within(preview).getByText('Your quote')).toBeInTheDocument()
    expect(within(preview).getByText('Coverage A: $500,000')).toBeInTheDocument()

    await userEvent.click(within(preview).getByRole('button', { name: 'Edit' }))
    const edit = within(screen.getByRole('form', { name: 'Edit' }))
    expect(edit.getByRole('button', { name: 'Edit' })).toBeDisabled()
    for (const [label, text] of [
      ['Subject', 'Your quote, checked'],
      ['Body', 'Checked.'],
      ['Reason', 'too stiff'],
    ]) {
      await userEvent.clear(edit.getByLabelText(label))
      await userEvent.type(edit.getByLabelText(label), text)
    }
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
})

describe('the other items of a lead', () => {
  it.each([
    ['Approve', { type: 'approve', payload: { item_id: 18, artifact_hash: null, reason: 'clear' } }],
    ['Reject', { type: 'reject', payload: { item_id: 18, reason: 'clear' } }],
  ])('%s a pending value with a reason, shown by the field’s label', async (name, body) => {
    const posted = stubApi()
    item(pendingItem)
    expect(screen.getByText('Months unoccupied: proposed 5, current 0')).toBeInTheDocument()
    expect(screen.queryByText(/months_unoccupied/)).toBeNull()

    await choose(name, 'clear')

    expect(posted).toEqual([{ path: '/api/commands', body }])
  })

  it('acknowledges a late-reply review but offers no reject', () => {
    item(lateReplyItem)
    expect(screen.getByRole('button', { name: 'Acknowledge' })).toBeEnabled()
    expect(screen.queryByRole('button', { name: 'Approve' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Reject' })).toBeNull()
  })

  it('offers no choice for a missing contact route and says when it closes', () => {
    item(noRouteItem)
    expect(screen.queryByRole('button')).toBeNull()
    expect(screen.getByText('This closes when a contact email is resolved.')).toBeInTheDocument()
  })

  it('says a wait for the producer closes when the producer replies', () => {
    item(producerWait)
    expect(screen.getByText('This closes when the producer replies.')).toBeInTheDocument()
    expect(screen.queryByText(/resolved|declined/)).toBeNull()
  })

  it('shows the refusal reason the command returns', async () => {
    stubApi({ accepted: false, event_id: null, reason: 'the cause persists' })
    item(pendingItem)
    await choose('Approve', 'clear')

    expect(await screen.findByRole('alert')).toHaveTextContent('the cause persists')
  })
})

describe('the question card', () => {
  it('shows the choice with the values it needs by label and every option enabled', () => {
    item(questionItem)
    const card = screen.getByRole('region', { name: 'I13.fire_fail' })
    expect(screen.getAllByText('The fire simulation failed: decline, or continue?')).toHaveLength(1)
    expect(within(card).getByText('Roof age: 12')).toBeInTheDocument()
    expect(within(card).getByText('Wall type: —')).toBeInTheDocument()
    const buttons = within(card).getAllByRole('button')
    expect(buttons.map((b) => b.textContent)).toEqual(['decline', 'legacy underwriting'])
    for (const button of buttons) expect(button).toBeEnabled()
  })

  it('posts the ruling only after an option is chosen and a reason is given', async () => {
    const posted = stubApi()
    item(questionItem)
    await userEvent.click(screen.getByRole('button', { name: 'legacy underwriting' }))
    expect(reasonForm().getByRole('button', { name: 'Choose legacy underwriting' })).toBeDisabled()
    expect(posted).toEqual([])

    await userEvent.type(reasonForm().getByLabelText('Reason'), 'the checklist is met')
    await userEvent.click(reasonForm().getByRole('button', { name: 'Choose legacy underwriting' }))

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
    await waitFor(() => expect(screen.queryByLabelText('Reason')).toBeNull())
  })
})
