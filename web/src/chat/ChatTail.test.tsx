// ABOUTME: Tests the chat tail and the composer: a source line under "Related artifacts" opens the panel on its citation, a card for another lead selects that lead, and Apply, Dismiss and a refusal reach the server.
// ABOUTME: The stubbed responses are typed objects of the generated API types, so a shape the backend does not serve fails the type check.
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { components } from '@/api/types'
import type { Turn } from '@/surface'
import { ChatTail } from './ChatTail'
import { Composer } from './Composer'

type Schemas = components['schemas']

const card: Schemas['ProposalView'] = {
  proposal_id: 4,
  lead_id: null,
  payload: {
    type: 'decline_lead',
    payload: { lead_id: 'LEAD-1', reason: 'vacant' },
    rationale: 'The building is vacant.',
  },
}

const handlers = { onOpen: () => {}, onSelect: () => {}, onChange: () => {} }

function respond(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
}

// Answers the two card routes and records each call.
function stubApi(apply: Schemas['CommandResponse'] | null) {
  const calls: string[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      calls.push(`${init?.method ?? 'GET'} ${String(input)}`)
      return respond(String(input).endsWith('/apply') ? apply : null)
    }),
  )
  return calls
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('ChatTail', () => {
  it('folds the answer’s sources under "Related artifacts", one line each that opens it in the panel', async () => {
    const turn: Turn = {
      message: 'How did it arrive?',
      steps: ['Read the lead.'],
      closing: {
        type: 'answer',
        answer: 'It arrived by web.',
        citations: [
          { number: 2, lead_id: 'LEAD-00000042-008', kind: 'fact', id: 15, text: 'Fact: Roof material' },
          { number: 1, lead_id: 'LEAD-00000042-008', kind: 'event', id: 12, text: 'Event: Review this notice before it is sent.' },
          { number: 3, lead_id: 'LEAD-00000042-000', kind: 'lead', id: 'LEAD-00000042-000', text: 'Lead: LEAD-000' },
        ],
      },
    }
    const onOpen = vi.fn()
    render(<ChatTail {...handlers} turns={[turn]} proposals={[]} leadId="LEAD-00000042-008" onOpen={onOpen} />)

    expect(screen.getByText('It arrived by web.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^Open source/ })).toBeNull()
    const fold = screen.getByText('Related artifacts (3)').closest('details')!
    expect(fold).not.toHaveAttribute('open')
    const sources = within(screen.getByRole('list', { name: 'Related artifacts' })).getAllByRole('listitem')
    expect(sources.map((source) => source.textContent)).toEqual([
      'Event: Review this notice before it is sent, lead 008',
      'Fact: Roof material, lead 008',
      'Lead: LEAD-000',
    ])
    await userEvent.click(screen.getByText('Related artifacts (3)'))
    await userEvent.click(within(sources[1]).getByRole('button'))

    expect(onOpen).toHaveBeenCalledExactlyOnceWith({ kind: 'fact', lead_id: 'LEAD-00000042-008', id: 15 })
  })

  it('shows a turn that has not closed as working, with its steps open', () => {
    const turn: Turn = { message: 'hello', steps: ['Read the queue.'], closing: null }
    render(<ChatTail {...handlers} turns={[turn]} proposals={[]} leadId={null} />)

    expect(screen.getByText('Working…')).toBeInTheDocument()
    expect(screen.getByText('Read the queue.')).toBeVisible()
  })

  it('shows the reason an error closed the turn', () => {
    const turn: Turn = { message: 'hello', steps: [], closing: { type: 'error', reason: 'no recording for skill chat' } }
    render(<ChatTail {...handlers} turns={[turn]} proposals={[]} leadId={null} />)

    expect(screen.getByRole('alert')).toHaveTextContent('Could not get an answer: no recording for skill chat.')
  })

  it('selects the lead a card was proposed on when it is not the open conversation', async () => {
    const turn: Turn = {
      message: 'decline lead 8',
      steps: [],
      closing: { type: 'proposal', proposal_id: 4, lead_id: 'LEAD-00000042-008', rationale: 'Vacant.' },
    }
    const onSelect = vi.fn()
    render(<ChatTail {...handlers} turns={[turn]} proposals={[]} leadId={null} onSelect={onSelect} />)

    await userEvent.click(screen.getByRole('button', { name: 'Proposed on Lead 008' }))

    expect(onSelect).toHaveBeenCalledWith('LEAD-00000042-008')
  })

  it('adds no line for a card that sits on the open lead', () => {
    const turn: Turn = {
      message: 'decline it',
      steps: [],
      closing: { type: 'proposal', proposal_id: 4, lead_id: 'LEAD-00000042-008', rationale: 'Vacant.' },
    }
    render(<ChatTail {...handlers} turns={[turn]} proposals={[]} leadId="LEAD-00000042-008" />)

    expect(screen.queryByRole('button')).toBeNull()
  })

  it('shows a card with its command and applies it, then tells the page to refetch', async () => {
    const calls = stubApi({ accepted: true, event_id: 31, reason: null })
    const onChange = vi.fn()
    render(<ChatTail {...handlers} turns={[]} proposals={[card]} leadId={null} onChange={onChange} />)

    const cards = screen.getByRole('list', { name: 'Proposals' })
    expect(within(cards).getByText('The building is vacant.')).toBeInTheDocument()
    expect(within(cards).getByText('Decline lead LEAD-1')).toBeInTheDocument()
    expect(within(cards).queryByText(/decline_lead|\{/)).toBeNull()
    await userEvent.click(within(cards).getByRole('button', { name: 'Apply' }))

    await vi.waitFor(() => expect(onChange).toHaveBeenCalled())
    expect(calls).toContain('POST /api/proposals/4/apply')
  })

  it('keeps a card whose command is refused and shows the reason', async () => {
    stubApi({ accepted: false, event_id: 31, reason: 'lead LEAD-1 is already final' })
    render(<ChatTail {...handlers} turns={[]} proposals={[card]} leadId={null} />)

    await userEvent.click(screen.getByRole('button', { name: 'Apply' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('lead LEAD-1 is already final')
    expect(screen.getByText('The building is vacant.')).toBeInTheDocument()
  })

  it('dismisses a card', async () => {
    const calls = stubApi(null)
    const onChange = vi.fn()
    render(<ChatTail {...handlers} turns={[]} proposals={[card]} leadId={null} onChange={onChange} />)

    await userEvent.click(screen.getByRole('button', { name: 'Dismiss' }))

    await vi.waitFor(() => expect(onChange).toHaveBeenCalled())
    expect(calls).toContain('POST /api/proposals/4/dismiss')
  })
})

describe('Composer', () => {
  it('sends the trimmed message and clears the box, and sends nothing when blank', async () => {
    const onSend = vi.fn()
    render(<Composer placeholder="Ask about the queue" disabled={false} note={null} onSend={onSend} />)
    const box = screen.getByRole('textbox', { name: 'Message' })

    await userEvent.type(box, '   {Enter}')
    expect(onSend).not.toHaveBeenCalled()
    await userEvent.type(box, '  hello  ')
    await userEvent.click(screen.getByRole('button', { name: 'Send' }))

    expect(onSend).toHaveBeenCalledExactlyOnceWith('hello')
    expect(box).toHaveValue('')
  })

  it('is disabled with the note that says why', () => {
    render(<Composer placeholder="Ask" disabled note="A turn is running." onSend={() => {}} />)

    expect(screen.getByRole('textbox', { name: 'Message' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled()
    expect(screen.getByText('A turn is running.')).toBeInTheDocument()
  })
})
