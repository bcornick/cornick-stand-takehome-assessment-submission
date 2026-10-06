// ABOUTME: Tests the demo panel against fetch stubbed at the boundary: loading the day asks before it clears a run, and the producers' replies post to the fixtures route and show a refusal's reason.
// ABOUTME: The run and the responses are typed objects of the generated API types.
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { components } from '@/api/types'
import { DemoPanel } from './DemoPanel'

type Schemas = components['schemas']

const run: Schemas['RunView'] = {
  run_id: 'run-1',
  mode: 'replay',
  seed: 42,
  sim_now: '2026-06-29T08:00:00.000000Z',
  first_pass_complete: true,
  example_prompts: [],
  summary: {
    quotes_sent: 0,
    follow_ups_sent: 0,
    declines_approved: 0,
    waiting_on_underwriter: 0,
    waiting_on_producer: 0,
    waiting_on_data: 0,
    delivery_unknown: 0,
  },
}

// Renders the panel and opens its card from the pill it starts as.
async function renderOpen(view: Schemas['RunView'] = run, onChange: () => void = () => undefined) {
  render(<DemoPanel run={view} onChange={onChange} />)
  await userEvent.click(screen.getByRole('button', { name: 'Demo controls' }))
}

function stubApi(body: unknown) {
  const calls: string[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      calls.push(`${init?.method ?? 'GET'} ${String(input)}`)
      return new Response(JSON.stringify(body), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    }),
  )
  return calls
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('DemoPanel', () => {
  it('starts the run at once when none is loaded', async () => {
    const calls = stubApi(run)
    const onChange = vi.fn()
    await renderOpen({ ...run, run_id: null }, onChange)
    expect(screen.getByText('No run loaded')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: "Load today's leads" }))
    expect(calls).toEqual(['POST /api/run/start?wait=true'])
    await vi.waitFor(() => expect(onChange).toHaveBeenCalled())
  })

  it('asks before clearing a loaded run, starts only on "Load anyway" and posts nothing on "Cancel"', async () => {
    const calls = stubApi(run)
    await renderOpen(run)

    await userEvent.click(screen.getByRole('button', { name: "Load today's leads" }))
    expect(screen.getByText('This clears the current day')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(calls).toEqual([])
    expect(screen.queryByText('This clears the current day')).toBeNull()

    await userEvent.click(screen.getByRole('button', { name: "Load today's leads" }))
    await userEvent.click(screen.getByRole('button', { name: 'Load anyway' }))
    expect(calls).toEqual(['POST /api/run/start?wait=true'])
    expect(screen.queryByText('This clears the current day')).toBeNull()
  })

  it("delivers the producers' replies and shows the reason of the first refused one", async () => {
    const calls = stubApi({
      replies: [
        { lead_id: 'LEAD-1', accepted: true, reason: null },
        { lead_id: 'LEAD-2', accepted: false, reason: 'The lead has no open ask.' },
      ],
    })
    await renderOpen(run)
    await userEvent.click(screen.getByRole('button', { name: "Deliver the producers' replies" }))
    expect(calls).toEqual(['POST /api/replies/fixtures'])
    expect(await screen.findByRole('alert')).toHaveTextContent('The lead has no open ask.')
  })

  it('starts as a pill, opens on a click and minimises again', async () => {
    stubApi({})
    render(<DemoPanel run={run} onChange={() => undefined} />)
    expect(screen.queryByRole('button', { name: "Load today's leads" })).toBeNull()
    await userEvent.click(screen.getByRole('button', { name: 'Demo controls' }))
    expect(screen.getByRole('button', { name: "Load today's leads" })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Minimise' }))
    expect(screen.getByRole('button', { name: 'Demo controls' })).toBeInTheDocument()
  })
})
