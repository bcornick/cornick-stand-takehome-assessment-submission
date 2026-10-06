// ABOUTME: Tests the chat panel against fetch stubbed at the boundary: a message posts with the open lead and its answer shows numbered citations, a proposal card shows its command, Apply submits that card, and Dismiss closes it.
// ABOUTME: The stubbed responses are typed objects of the generated API types, so a shape the backend does not serve fails the type check.
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { components } from '@/api/types'
import { ChatPanel } from './ChatPanel'

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

const sse = (...events: unknown[]) => events.map((event) => `data: ${JSON.stringify(event)}\n\n`).join('')

function respond(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
}

// Answers the chat routes; `proposals` is what GET /api/proposals serves now, `apply` what Apply returns.
function stubApi(options: { proposals: Schemas['ProposalView'][]; answer?: string; apply?: Schemas['CommandResponse'] }) {
  const calls: string[] = []
  const bodies: unknown[] = []
  let proposals = options.proposals
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input)
      calls.push(`${init?.method ?? 'GET'} ${path}`)
      if (init?.body !== undefined) bodies.push(JSON.parse(String(init.body)))
      if (path === '/api/proposals') return respond(proposals)
      if (path === '/api/chat') return new Response(options.answer, { status: 200, headers: { 'Content-Type': 'text/event-stream' } })
      if (path === '/api/proposals/4/apply') {
        if (options.apply?.accepted) proposals = []
        return respond(options.apply)
      }
      if (path === '/api/proposals/4/dismiss') {
        proposals = []
        return respond(null)
      }
      return new Response('{}', { status: 404 })
    }),
  )
  return { calls, bodies }
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('ChatPanel', () => {
  it('posts the message with the open lead and shows the answer with numbered citations', async () => {
    const { bodies } = stubApi({
      proposals: [],
      answer: sse(
        { type: 'step', summary: 'Read the lead.' },
        {
          type: 'answer',
          answer: 'It arrived by web.',
          citations: [
            { number: 1, lead_id: 'LEAD-1', kind: 'event', id: 12 },
            { number: 2, lead_id: 'LEAD-1', kind: 'event', id: 15 },
          ],
        },
      ),
    })
    render(<ChatPanel leadId="LEAD-1" onChange={() => {}} />)

    await userEvent.type(screen.getByRole('textbox', { name: 'Message' }), 'How did it arrive?')
    await userEvent.click(screen.getByRole('button', { name: 'Send' }))

    expect(await screen.findByText('It arrived by web.')).toBeInTheDocument()
    expect(screen.getByText('[1]')).toBeInTheDocument()
    expect(screen.getByText('[2]')).toBeInTheDocument()
    expect(screen.queryByText('Working…')).toBeNull()
    expect(bodies[0]).toEqual({ message: 'How did it arrive?', lead_id: 'LEAD-1', history: [] })
  })

  it('shows the steps of a turn before its closing event arrives', async () => {
    const encoder = new TextEncoder()
    let stream!: ReadableStreamDefaultController<Uint8Array>
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) =>
      String(input) === '/api/proposals'
        ? respond([])
        : new Response(new ReadableStream<Uint8Array>({ start: (controller) => { stream = controller } }), { status: 200 })))
    render(<ChatPanel leadId={null} onChange={() => {}} />)

    await userEvent.type(screen.getByRole('textbox', { name: 'Message' }), 'hello')
    await userEvent.click(screen.getByRole('button', { name: 'Send' }))
    await vi.waitFor(() => expect(stream).toBeDefined())
    stream.enqueue(encoder.encode(sse({ type: 'step', summary: 'Read the queue.' })))

    expect(await screen.findByText('Read the queue.')).toBeInTheDocument()
    expect(screen.getByText('Working…')).toBeInTheDocument()

    stream.enqueue(encoder.encode(sse({ type: 'proposal', proposal_id: 4, lead_id: null })))
    stream.close()
    expect(await screen.findByText('Proposed. Review the card below.')).toBeInTheDocument()
    expect(screen.queryByText('Working…')).toBeNull()
  })

  it('shows a card with its command and applies it, then tells the page to refetch', async () => {
    const { calls } = stubApi({
      proposals: [card],
      apply: { accepted: true, event_id: 31, reason: null },
    })
    const onChange = vi.fn()
    render(<ChatPanel leadId={null} onChange={onChange} />)

    const cards = await screen.findByRole('list', { name: 'Proposals' })
    expect(within(cards).getByText('The building is vacant.')).toBeInTheDocument()
    expect(within(cards).getByText('Decline lead LEAD-1')).toBeInTheDocument()
    expect(within(cards).queryByText(/decline_lead|\{/)).toBeNull()
    await userEvent.click(within(cards).getByRole('button', { name: 'Apply' }))

    await vi.waitFor(() => expect(screen.queryByRole('list', { name: 'Proposals' })).toBeNull())
    expect(calls).toContain('POST /api/proposals/4/apply')
    expect(onChange).toHaveBeenCalled()
  })

  it('keeps a card whose command is refused and shows the reason', async () => {
    stubApi({ proposals: [card], apply: { accepted: false, event_id: 31, reason: 'lead LEAD-1 is already final' } })
    render(<ChatPanel leadId={null} onChange={() => {}} />)

    await userEvent.click(await screen.findByRole('button', { name: 'Apply' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('lead LEAD-1 is already final')
    expect(screen.getByText('The building is vacant.')).toBeInTheDocument()
  })

  it('dismisses a card', async () => {
    const { calls } = stubApi({ proposals: [card] })
    render(<ChatPanel leadId={null} onChange={() => {}} />)

    await userEvent.click(await screen.findByRole('button', { name: 'Dismiss' }))

    await vi.waitFor(() => expect(screen.queryByText('The building is vacant.')).toBeNull())
    expect(calls).toContain('POST /api/proposals/4/dismiss')
  })

  it('shows the reason the server gives for a message that got no answer', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) =>
      String(input) === '/api/proposals'
        ? respond([])
        : new Response(JSON.stringify({ detail: 'no recording for skill chat' }), { status: 409 })))
    render(<ChatPanel leadId={null} onChange={() => {}} />)

    await userEvent.type(screen.getByRole('textbox', { name: 'Message' }), 'hello')
    await userEvent.click(screen.getByRole('button', { name: 'Send' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('no recording for skill chat')
  })

  it('names the route and the status when the server gives no reason', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) =>
      String(input) === '/api/proposals' ? respond([]) : new Response('Bad gateway', { status: 502 })))
    render(<ChatPanel leadId={null} onChange={() => {}} />)

    await userEvent.type(screen.getByRole('textbox', { name: 'Message' }), 'hello')
    await userEvent.click(screen.getByRole('button', { name: 'Send' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('/api/chat answered 502')
  })
})
