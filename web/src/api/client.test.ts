// ABOUTME: Tests the chat stream reader: events split across chunks and separated by comment pings arrive once each, in order.
// ABOUTME: The body is a real ReadableStream behind a stubbed fetch.
import { afterEach, expect, it, vi } from 'vitest'
import { streamChat, type ChatEvent } from './client'

afterEach(() => {
  vi.unstubAllGlobals()
})

it('yields each event once and in order when chunks split an event and a ping sits between events', async () => {
  const text =
    'data: {"type":"step","summary":"Read the lead."}\n\n: ping\n\n' +
    'data: {"type":"answer","answer":"Done.","citations":[]}\n\n'
  const cut = text.indexOf('"summary"') + 4
  const cutAgain = text.indexOf('Done.') + 2
  const encoder = new TextEncoder()
  const chunks = [text.slice(0, cut), text.slice(cut, cutAgain), text.slice(cutAgain)]
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      chunks.forEach((chunk) => controller.enqueue(encoder.encode(chunk)))
      controller.close()
    },
  })
  vi.stubGlobal('fetch', vi.fn(async () => new Response(body, { status: 200 })))

  const events: ChatEvent[] = []
  await streamChat({ message: 'hi', history: [] }, (event) => events.push(event))

  expect(events).toEqual([
    { type: 'step', summary: 'Read the lead.' },
    { type: 'answer', answer: 'Done.', citations: [] },
  ])
})
