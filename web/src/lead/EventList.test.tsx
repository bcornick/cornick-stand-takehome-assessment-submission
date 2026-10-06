// ABOUTME: Tests the event list against fetch stubbed at the boundary: each event shows its id, a plain label for its type, who acted in words, a local-looking time and its one-line summary.
// ABOUTME: The events are typed objects of the generated API types, so a shape the backend does not serve fails the type check.
import { render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import type { components } from '@/api/types'
import { EventList } from './EventList'

const events: components['schemas']['LeadEvents'] = {
  lead_id: 'LEAD-1',
  events: [
    {
      id: 7,
      type: 'fact_observed',
      actor: 'workflow',
      sim_ts: '2026-06-29T08:00:00.000000Z',
      summary: 'roof_year recorded as 2017 (submitted).',
    },
    {
      id: 9,
      type: 'message_sent',
      actor: 'underwriter',
      sim_ts: '2026-06-29T09:30:00.000000Z',
      summary: 'The message was posted to the mailbox.',
    },
  ],
}

afterEach(() => {
  vi.unstubAllGlobals()
})

it('shows a plain label, the actor in words, a local time and the summary of each event', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => new Response(JSON.stringify(events), { status: 200 })),
  )
  render(<EventList leadId="LEAD-1" refresh={0} />)

  const rows = await screen.findAllByRole('listitem')

  expect(rows[0]).toHaveTextContent('#7 Fact observed The system, ')
  expect(rows[0]).toHaveTextContent('roof_year recorded as 2017 (submitted).')
  expect(rows[1]).toHaveTextContent('#9 Message sent The underwriter, ')
  for (const row of rows) {
    expect(row.textContent).not.toMatch(/T\d\d:\d\d|workflow/)
    expect(row.textContent).toMatch(/[A-Z][a-z]{2} \d{1,2}, 2026, \d{1,2}:\d\d [AP]M/)
  }
})
