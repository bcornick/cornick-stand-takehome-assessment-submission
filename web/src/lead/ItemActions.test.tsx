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
  asks: [],
  sent_at: null,
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
  readings: {
    'I13.fire_fail': {
      roof_age: { text: 'Fails: above 0.50', problem: true },
      wall_type: { text: 'Passes', problem: false },
    },
  },
  fields: [
    { key: 'months_unoccupied', label: 'Months unoccupied', section: 'Property', kind: 'number', options: [] },
    { key: 'roof_age', label: 'Roof age', section: 'Construction', kind: 'number', options: [] },
    { key: 'wall_type', label: 'Wall type', section: 'Construction', kind: 'text', options: [] },
  ],
  missing_fields: [],
  decline_reason: null,
  decline_reason_on_file: false,
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

// The notes form that opens under the buttons once a choice is made.
function reasonForm() {
  return within(screen.getByRole('form', { name: 'Confirm the choice' }))
}

async function choose(name: string, note: string, confirm = name) {
  await userEvent.click(screen.getByRole('button', { name }))
  if (note !== '') await userEvent.type(reasonForm().getByLabelText('Notes'), note)
  await userEvent.click(reasonForm().getByRole('button', { name: confirm }))
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('a draft card', () => {
  it('shows one notes field only after Approve is chosen, then approves against the hash shown with no note', async () => {
    const posted = stubApi()
    item(packetItem)
    expect(screen.getByRole('button', { name: 'Send quote' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Reject' })).toBeEnabled()
    expect(screen.queryByRole('button', { name: 'Approve' })).toBeNull()
    expect(screen.queryByLabelText('Notes')).toBeNull()

    await userEvent.click(screen.getByRole('button', { name: 'Send quote' }))
    expect(screen.getAllByLabelText('Notes')).toHaveLength(1)
    expect(screen.getByPlaceholderText('Optional. Anything the file should carry about this quote.')).toBeInTheDocument()
    expect(reasonForm().getByRole('button', { name: 'Send quote' })).toBeEnabled()

    await userEvent.click(reasonForm().getByRole('button', { name: 'Send quote' }))

    expect(posted).toEqual([
      {
        path: '/api/commands',
        body: {
          type: 'approve',
          payload: { item_id: 17, artifact_hash: packet.payload_hash, reason: '' },
        },
      },
    ])
  })

  it('rejects a draft with the note typed', async () => {
    const posted = stubApi()
    item(packetItem)
    await userEvent.click(screen.getByRole('button', { name: 'Reject' }))
    expect(reasonForm().getByRole('button', { name: 'Reject' })).toBeEnabled()

    await userEvent.type(reasonForm().getByLabelText('Notes'), 'the roof is wrong')
    await userEvent.click(reasonForm().getByRole('button', { name: 'Reject' }))

    expect(posted[0]).toEqual({
      path: '/api/commands',
      body: { type: 'reject', payload: { item_id: 17, reason: 'the roof is wrong' } },
    })
  })

  it('replaces the choices with the chosen one’s form, one button per action, and Cancel brings them back', async () => {
    const posted = stubApi()
    item(packetItem)
    await userEvent.click(screen.getByRole('button', { name: 'Reject' }))
    expect(screen.queryByRole('button', { name: 'Send quote' })).toBeNull()
    expect(screen.getAllByRole('button', { name: 'Reject' })).toHaveLength(1)
    await userEvent.click(reasonForm().getByRole('button', { name: 'Cancel' }))

    expect(screen.queryByLabelText('Notes')).toBeNull()
    expect(screen.getByRole('button', { name: 'Send quote' })).toBeInTheDocument()
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
    await userEvent.type(reasonForm().getByLabelText('Notes'), 'the roof is fine')
    await userEvent.click(reasonForm().getByRole('button', { name: 'Withdraw decline and send the asks' }))

    expect(posted[0].body).toEqual({ type: 'reject', payload: { item_id: 30, reason: 'the roof is fine' } })
  })

  it('names a request’s preview and sends it with Send request', async () => {
    const request: Schemas['DraftView'] = { ...packet, intent_id: 'intent-request', kind: 'routine_request' }
    const posted = stubApi()
    item(
      blocker(31, 'underwriter_review', {
        item_kind: 'draft',
        intent_id: request.intent_id,
        text: 'Not sent yet, in case you decline this lead. Send it to the producer, or decline this lead.',
      }),
      { ...lead, drafts: [request] },
    )
    expect(screen.getByText('Preview or edit the request')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Reject' })).toBeNull()
    expect(screen.getByText('Not sent yet, in case you decline this lead. Send it to the producer, or decline this lead.')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Send request' }))
    await userEvent.click(reasonForm().getByRole('button', { name: 'Send request' }))

    expect(posted[0].body).toEqual({
      type: 'approve',
      payload: { item_id: 31, artifact_hash: request.payload_hash, reason: '' },
    })
  })

  it('discards a request, saying nothing is sent, with an optional note', async () => {
    const request: Schemas['DraftView'] = { ...packet, intent_id: 'intent-request', kind: 'routine_request' }
    const posted = stubApi()
    item(
      blocker(31, 'underwriter_review', { item_kind: 'draft', intent_id: request.intent_id, text: 'Not sent yet.' }),
      { ...lead, drafts: [request] },
    )
    await userEvent.click(screen.getByRole('button', { name: 'Discard request' }))
    expect(screen.getByText(/Nothing is sent to the producer/)).toBeInTheDocument()
    await userEvent.click(reasonForm().getByRole('button', { name: 'Discard request' }))

    expect(posted[0].body).toEqual({ type: 'reject', payload: { item_id: 31, reason: '' } })
  })

  it('says why the lead is declined on the decline notice card', () => {
    item(
      blocker(30, 'underwriter_review', { item_kind: 'draft', intent_id: decline.intent_id, text: 'Review the notice.' }),
      { ...lead, drafts: [decline], decline_reason: 'Foundation Type is Piers, so the post and pier page declines it (PP-1)' },
    )
    expect(screen.getByText('Why: Foundation Type is Piers, so the post and pier page declines it (PP-1).')).toBeInTheDocument()
  })

  it('approves a decline notice only with the reason for the decline', async () => {
    const posted = stubApi()
    item(
      blocker(30, 'underwriter_review', { item_kind: 'draft', intent_id: decline.intent_id, text: 'Review the notice.' }),
      { ...lead, drafts: [decline] },
    )
    expect(screen.queryByRole('button', { name: 'Approve' })).toBeNull()
    const send = screen.getByRole('button', { name: 'Send decline notice' })
    expect(send).toHaveClass('button-destructive')
    await userEvent.click(send)
    expect(screen.queryByLabelText('Notes')).toBeNull()
    expect(screen.getByPlaceholderText('Required. Why this lead is declined; kept on file.')).toBeInTheDocument()
    expect(reasonForm().getByRole('button', { name: 'Send decline notice' })).toBeDisabled()
    expect(reasonForm().getByRole('button', { name: 'Send decline notice' })).toHaveClass('button-destructive')

    await userEvent.type(reasonForm().getByLabelText('Reason for the decline, kept on file'), 'outside appetite')
    await userEvent.click(reasonForm().getByRole('button', { name: 'Send decline notice' }))

    expect(posted[0].body).toEqual({
      type: 'approve',
      payload: { item_id: 30, artifact_hash: decline.payload_hash, reason: 'outside appetite' },
    })
  })

  it('sends a decline notice with no reason when the ruling that declined the lead gave one', async () => {
    const posted = stubApi()
    item(
      blocker(30, 'underwriter_review', { item_kind: 'draft', intent_id: decline.intent_id, text: 'Review the notice.' }),
      { ...lead, drafts: [decline], decline_reason_on_file: true },
    )
    await userEvent.click(screen.getByRole('button', { name: 'Send decline notice' }))
    expect(screen.queryByLabelText('Reason for the decline, kept on file')).toBeNull()
    await userEvent.click(reasonForm().getByRole('button', { name: 'Send decline notice' }))

    expect(posted[0].body).toEqual({
      type: 'approve',
      payload: { item_id: 30, artifact_hash: decline.payload_hash, reason: '' },
    })
  })

  it.each([
    ['routine_request', 'Send request'],
    ['sensitive_request', 'Send request'],
  ] as const)('names the approval of a %s as sending it', (kind, label) => {
    item(packetItem, { ...lead, drafts: [{ ...packet, kind }] })
    expect(screen.getByRole('button', { name: label })).toBeEnabled()
  })

  it('shows no owner badge beside the kind of the item', () => {
    item(packetItem)
    expect(screen.getByText('Underwriter review')).toBeInTheDocument()
    expect(screen.queryByText(/^Waits on/)).toBeNull()
  })

  it('folds the subject and body in a preview, and Edit inside it opens a form whose Save edits posts the new text with no reason', async () => {
    const posted = stubApi()
    item(packetItem)
    const preview = screen.getByText('Preview the packet').closest('details')!
    expect(preview).not.toHaveAttribute('open')
    expect(within(preview).getByText('Your quote')).toBeInTheDocument()
    expect(within(preview).getByText('Coverage A: $500,000')).toBeInTheDocument()

    await userEvent.click(within(preview).getByRole('button', { name: 'Edit' }))
    const edit = within(screen.getByRole('form', { name: 'Save edits' }))
    expect(edit.queryByLabelText('Reason')).toBeNull()
    for (const [label, text] of [
      ['Subject', 'Your quote, checked'],
      ['Body', 'Checked.'],
    ]) {
      await userEvent.clear(edit.getByLabelText(label))
      await userEvent.type(edit.getByLabelText(label), text)
    }
    await userEvent.click(edit.getByRole('button', { name: 'Save edits' }))

    expect(posted).toEqual([
      {
        path: '/api/commands',
        body: {
          type: 'edit_draft',
          payload: {
            intent_id: packet.intent_id,
            subject: 'Your quote, checked',
            body: 'Checked.',
            reason: '',
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
  ])('%s a pending value with a note, shown by the field’s label', async (name, body) => {
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
    await choose('Approve', '')

    expect(await screen.findByRole('alert')).toHaveTextContent('the cause persists')
  })
})

describe('the question card', () => {
  it('shows the choice with the values it needs by label and every option enabled', () => {
    item(questionItem)
    const card = screen.getByRole('region', { name: 'I13.fire_fail' })
    expect(screen.getAllByText('The fire simulation failed: decline, or continue?')).toHaveLength(1)
    expect(within(card).getByText('Roof age: 12')).toBeInTheDocument()
    expect(within(card).getByText('Wall type: Not provided')).toBeInTheDocument()
    const buttons = within(card).getAllByRole('button')
    expect(buttons.map((b) => b.textContent)).toEqual(['Decline', 'Legacy underwriting'])
    for (const button of buttons) expect(button).toBeEnabled()
    expect(buttons[0]).toHaveClass('button-destructive')
    expect(buttons[1]).toHaveClass('button-outline')
  })

  it('shows what the playbook makes of each value, a problem in the accent', () => {
    item(questionItem)
    const card = within(screen.getByRole('region', { name: 'I13.fire_fail' }))
    expect(card.getByText('· Fails: above 0.50')).toHaveClass('text-accent')
    expect(card.getByText('· Passes')).not.toHaveClass('text-accent')
  })

  it('asks for the reason for the decline when Decline is chosen, and posts it', async () => {
    const posted = stubApi()
    item(questionItem)
    await userEvent.click(screen.getByRole('button', { name: 'Decline' }))
    const confirm = reasonForm().getByRole('button', { name: 'Choose decline' })
    expect(confirm).toBeDisabled()
    expect(screen.getByPlaceholderText('Required. Why this lead is declined; kept on file.')).toBeInTheDocument()
    await userEvent.type(reasonForm().getByLabelText('Reason for the decline, kept on file'), 'too steep')
    await userEvent.click(confirm)

    expect(posted[0].body).toEqual({
      type: 'record_ruling',
      payload: { lead_id: 'LEAD-1', choice_id: 'I13.fire_fail', option: 'decline', reason: 'too steep' },
    })
  })

  it('posts the ruling after an option is chosen, with no note', async () => {
    const posted = stubApi()
    item(questionItem)
    await userEvent.click(screen.getByRole('button', { name: 'Legacy underwriting' }))
    expect(posted).toEqual([])
    expect(screen.getByPlaceholderText('Optional. What tipped the choice, e.g. 14 ft to the neighbour.')).toBeInTheDocument()
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
            reason: '',
          },
        },
      },
    ])
    await waitFor(() => expect(screen.queryByLabelText('Notes')).toBeNull())
  })
})
