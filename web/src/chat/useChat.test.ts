// ABOUTME: Tests the chat tails against fetch stubbed at the boundary: a turn's steps show before its closing event, history carries a conversation's closed turns only, and a new run clears the tails.
// ABOUTME: A card's rationale is read from the server's proposals; a transport or HTTP failure closes the turn as an error with the server's reason.
import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import type { components } from '@/api/types'
import { QUEUE, type Chat } from '@/surface'
import { useChat } from './useChat'

type Schemas = components['schemas']

const sse = (...events: unknown[]) => events.map((event) => `data: ${JSON.stringify(event)}\n\n`).join('')

const answer = (text: string) => ({ type: 'answer', answer: text, citations: [] })

const card: Schemas['ProposalView'] = {
  proposal_id: 4,
  lead_id: null,
  payload: { type: 'decline_lead', payload: { lead_id: 'LEAD-1', reason: 'vacant' }, rationale: 'The building is vacant.' },
}

// Answers /api/chat with the next of `streams`, recording each request body; /api/proposals serves `proposals`.
function stubApi(streams: string[], proposals: Schemas['ProposalView'][] = []) {
  const bodies: Schemas['ChatRequest'][] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (String(input) === '/api/proposals') return new Response(JSON.stringify(proposals), { status: 200 })
      bodies.push(JSON.parse(String(init?.body)))
      return new Response(streams[bodies.length - 1], { status: 200 })
    }),
  )
  return bodies
}

// Sends one message and waits until no turn is in flight.
async function sendAndSettle(result: { current: Chat }, send: (chat: Chat) => void) {
  act(() => {
    send(result.current)
  })
  await waitFor(() => expect(result.current.running).toBe(false))
}

// React reports state changes outside a rendered component only when the environment says it supports act.
beforeAll(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('useChat', () => {
  it('shows the steps of a turn before its closing event arrives', async () => {
    const encoder = new TextEncoder()
    let stream!: ReadableStreamDefaultController<Uint8Array>
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(new ReadableStream<Uint8Array>({ start: (controller) => { stream = controller } }), { status: 200 })),
    )
    const { result } = renderHook(() => useChat('run-1', () => {}))

    act(() => {
      result.current.send(QUEUE, 'hello')
    })
    await waitFor(() => expect(stream).toBeDefined())
    stream.enqueue(encoder.encode(sse({ type: 'step', summary: 'Read the queue.' })))

    await waitFor(() => expect(result.current.turnsOf(QUEUE)[0].steps).toEqual(['Read the queue.']))
    expect(result.current.turnsOf(QUEUE)[0].closing).toBeNull()
    expect(result.current.running).toBe(true)

    stream.enqueue(encoder.encode(sse(answer('Done.'))))
    stream.close()
    await waitFor(() => expect(result.current.running).toBe(false))
    expect(result.current.turnsOf(QUEUE)[0].closing).toEqual(answer('Done.'))
  })

  it('carries the first exchange of a conversation as history, and no other conversation', async () => {
    const bodies = stubApi([sse(answer('One.')), sse(answer('Two.')), sse(answer('Three.'))])
    const { result } = renderHook(() => useChat('run-1', () => {}))

    await sendAndSettle(result, (chat) => chat.send('LEAD-1', 'first'))
    await sendAndSettle(result, (chat) => chat.send('LEAD-1', 'second'))
    await sendAndSettle(result, (chat) => chat.send(QUEUE, 'third'))

    expect(bodies[0]).toEqual({ message: 'first', lead_id: 'LEAD-1', history: [] })
    expect(bodies[1].history).toEqual([{ message: 'first', reply: 'One.' }])
    expect(bodies[2]).toEqual({ message: 'third', lead_id: null, history: [] })
  })

  it('keeps the last four closed turns and cuts long text to the length the server accepts', async () => {
    const long = 'x'.repeat(2500)
    const bodies = stubApi(Array.from({ length: 6 }, (_, index) => sse(answer(index === 0 ? long : `reply ${index}`))))
    const { result } = renderHook(() => useChat('run-1', () => {}))

    for (const message of [long, 'm1', 'm2', 'm3', 'm4', 'm5']) await sendAndSettle(result, (chat) => chat.send(QUEUE, message))

    expect(bodies[5].history.map((exchange) => exchange.message)).toEqual(['m1', 'm2', 'm3', 'm4'])
    expect(bodies[1].history[0]).toEqual({ message: 'x'.repeat(2000), reply: 'x'.repeat(2000) })
  })

  it('clears the tails when the run changes', async () => {
    stubApi([sse(answer('One.'))])
    const { result, rerender } = renderHook(({ runId }) => useChat(runId, () => {}), { initialProps: { runId: 'run-1' } })

    await sendAndSettle(result, (chat) => chat.send(QUEUE, 'first'))
    expect(result.current.turnsOf(QUEUE)).toHaveLength(1)
    rerender({ runId: 'run-2' })

    await waitFor(() => expect(result.current.turnsOf(QUEUE)).toEqual([]))
  })

  it('stores a card with its rationale and tells the page to refetch', async () => {
    stubApi([sse({ type: 'proposal', proposal_id: 4, lead_id: null })], [card])
    const onProposal = vi.fn()
    const { result } = renderHook(() => useChat('run-1', onProposal))

    await sendAndSettle(result, (chat) => chat.send(QUEUE, 'decline it'))

    expect(result.current.turnsOf(QUEUE)[0].closing).toEqual({
      type: 'proposal',
      proposal_id: 4,
      lead_id: null,
      rationale: 'The building is vacant.',
    })
    expect(onProposal).toHaveBeenCalled()
  })

  it('closes a turn with the reason the server gives for a message that got no answer', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ detail: 'no recording for skill chat' }), { status: 409 })))
    const { result } = renderHook(() => useChat('run-1', () => {}))

    await sendAndSettle(result, (chat) => chat.send(QUEUE, 'hello'))

    expect(result.current.turnsOf(QUEUE)[0].closing).toEqual({ type: 'error', reason: 'no recording for skill chat' })
  })

  it('names the route and the status when the server gives no reason', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('Bad gateway', { status: 502 })))
    const { result } = renderHook(() => useChat('run-1', () => {}))

    await sendAndSettle(result, (chat) => chat.send(QUEUE, 'hello'))

    expect(result.current.turnsOf(QUEUE)[0].closing).toMatchObject({ type: 'error', reason: expect.stringContaining('/api/chat answered 502') })
  })
})
