// ABOUTME: Tests the app shell with fetch stubbed at the boundary to answer from the ui fixtures.
// ABOUTME: Covers loading, the queue, opening a lead's detail pane, and a plain message when a request fails.
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { details, rows, run } from '@/test/fixtures'

function respond(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

// Answers the three read routes from the fixtures; `fail` makes a route answer 501 as the live app does.
function stubApi(fail: string[] = []) {
  const calls: string[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input)
      calls.push(path)
      if (fail.includes(path)) return respond({ detail: 'not implemented' }, 501)
      if (path === '/api/run') return respond(run)
      if (path === '/api/leads') return respond(rows)
      const lead = details[path.replace('/api/leads/', '')]
      if (lead) return respond(lead)
      return respond({ detail: 'not found' }, 404)
    }),
  )
  return calls
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('App', () => {
  it('shows a loading message, then the queue', async () => {
    stubApi()
    render(<App />)
    expect(screen.getByRole('status')).toHaveTextContent('Loading the queue')
    expect(await screen.findByRole('button', { name: rows[0]!.lead_id })).toBeInTheDocument()
    expect(screen.getAllByRole('table')).toHaveLength(2)
  })

  it('opens the detail pane of the selected lead', async () => {
    const calls = stubApi()
    render(<App />)
    await userEvent.click(await screen.findByRole('button', { name: 'LEAD-00000042-003' }))
    const lead = details['LEAD-00000042-003']!
    const pane = await screen.findByRole('article')
    expect(within(pane).getByRole('heading', { name: 'LEAD-00000042-003' })).toBeInTheDocument()
    expect(within(pane).getByText(lead.next_action!)).toBeInTheDocument()
    expect(calls).toContain('/api/leads/LEAD-00000042-003')
    expect(calls.some((path) => path.includes('/events/stream'))).toBe(false)
  })

  it('replaces the pane when another lead is selected', async () => {
    stubApi()
    render(<App />)
    await userEvent.click(await screen.findByRole('button', { name: 'LEAD-00000042-003' }))
    await userEvent.click(await screen.findByRole('button', { name: 'LEAD-00000042-000' }))
    const pane = await screen.findByRole('heading', { name: 'LEAD-00000042-000', level: 2 })
    expect(pane).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'LEAD-00000042-003', level: 2 })).not.toBeInTheDocument()
  })

  it('shows a plain message when the queue cannot be loaded', async () => {
    stubApi(['/api/leads'])
    render(<App />)
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Could not load the queue')
    expect(alert).toHaveTextContent('/api/leads answered 501')
  })

  it('shows a plain message when a lead cannot be loaded, and keeps the queue', async () => {
    stubApi(['/api/leads/LEAD-00000042-003'])
    render(<App />)
    await userEvent.click(await screen.findByRole('button', { name: 'LEAD-00000042-003' }))
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Could not load LEAD-00000042-003')
    expect(alert).toHaveTextContent('answered 501')
    expect(screen.getAllByRole('table')).toHaveLength(2)
  })
})
