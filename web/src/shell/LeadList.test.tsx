// ABOUTME: Tests the lead list: leads appear in the order served under their group headings, the selected entry is current, a lead without an address says so, and a click reports the conversation key.
// ABOUTME: The run and the rows are typed objects of the generated API types.
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { components } from '@/api/types'
import { QUEUE } from '@/surface'
import { LeadList } from './LeadList'

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
    follow_ups_sent: 1,
    declines_approved: 0,
    waiting_on_underwriter: 1,
    waiting_on_producer: 1,
    waiting_on_data: 0,
    delivery_unknown: 0,
  },
}

const row: Schemas['QueueRow'] = {
  lead_id: 'LEAD-00000042-008',
  label: '8924 Lakeview Blvd',
  status: 'in_progress',
  primary_next_action: 'underwriter_review',
  waits_on: 'underwriter',
  age_business_days: 0.5,
  service_level_breached: false,
  effective_date: '2026-07-23',
  ask_count: 2,
  decision: 'Review quote',
  request_round: null,
  asked_at: null,
  group: 'blocked_on_underwriter',
}
const rows: Schemas['QueueRow'][] = [
  { ...row, lead_id: 'LEAD-00000042-009', label: '1 Elm St' },
  row,
  {
    ...row,
    lead_id: 'LEAD-00000042-001',
    label: 'LEAD-00000042-001',
    primary_next_action: 'producer_reply',
    waits_on: 'producer',
    decision: null,
    request_round: 1,
    asked_at: '2026-07-03T09:30:00.000000Z',
    service_level_breached: true,
    group: 'waiting_on_data_or_producer',
  },
]

describe('LeadList', () => {
  it('lists the leads in the order served under their group headings and marks the selected one', () => {
    render(<LeadList run={run} rows={rows} selected={row.lead_id} onSelect={() => undefined} />)
    const blocked = screen.getByRole('region', { name: 'Waiting on the underwriter' })
    const waiting = screen.getByRole('region', { name: 'Waiting on the producer or data' })
    expect(screen.queryByRole('region', { name: 'Finished' })).toBeNull()

    const buttons = within(blocked).getAllByRole('button')
    expect(buttons.map((button) => button.textContent)).toEqual([
      expect.stringContaining('Lead 009'),
      expect.stringContaining('Lead 008'),
    ])
    expect(within(blocked).getAllByText('Review quote')).toHaveLength(2)
    expect(within(waiting).getByText('2 asks · round 1')).toBeInTheDocument()
    expect(within(waiting).getByText(/Past service level/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Lead 008/ })).toHaveAttribute('aria-current', 'true')
    expect(screen.getByRole('button', { name: /Lead 009/ })).not.toHaveAttribute('aria-current')
  })

  it.each<[string, Partial<Schemas['QueueRow']>, string | null]>([
    ['the underwriter', {}, 'Review quote'],
    ['a choice', { decision: 'Fire simulation choice' }, null],
    ['the producer', { waits_on: 'producer', decision: null, ask_count: 1, request_round: 2 }, '1 ask · round 2'],
    ['a producer with no request out', { waits_on: 'producer', decision: null }, 'Waiting on producer'],
    ['data', { waits_on: 'data_team', decision: null }, 'Waiting on data'],
    ['a sent quote', { status: 'quote_sent', waits_on: null, decision: null }, 'Quote sent'],
    ['a decline', { status: 'declined', waits_on: null, decision: null }, 'Declined'],
    ['nothing', { waits_on: null, decision: null }, null],
  ])('chips a lead waiting on %s', (_name, change, chip) => {
    render(<LeadList run={run} rows={[{ ...row, ...change }]} selected={QUEUE} onSelect={() => undefined} />)
    const entry = screen.getByRole('button', { name: /Lead 008/ })
    const labels = ['Review quote', '1 ask · round 2', 'Waiting on producer', 'Waiting on data', 'Quote sent', 'Declined', 'In progress']
    for (const label of labels) {
      if (label === chip) expect(within(entry).getByText(label)).toBeInTheDocument()
      else expect(within(entry).queryByText(label)).toBeNull()
    }
  })

  it('says when the request went out, in place of the queue age, for a lead waiting on the producer', () => {
    const asked = { waits_on: 'producer', decision: null, request_round: 1, asked_at: '2026-07-03T09:30:00.000000Z' } as const
    render(
      <LeadList run={run} rows={[{ ...row, ...asked, age_business_days: 3.2, service_level_breached: true }]} selected={QUEUE} onSelect={() => undefined} />,
    )
    expect(screen.getByText('Effective Jul 23 · asked Jul 3 · Past service level')).toBeInTheDocument()
  })

  it.each<[number, string]>([
    [0.4, 'in queue today'],
    [1, '1 day in queue'],
    [3.2, '3 days in queue'],
  ])('words an age of %s business days as "%s" beside the effective date', (age, wording) => {
    render(
      <LeadList run={run} rows={[{ ...row, age_business_days: age }]} selected={QUEUE} onSelect={() => undefined} />,
    )
    expect(screen.getByText(`Effective Jul 23 · ${wording}`)).toBeInTheDocument()
  })

  it('says there is no effective date, and leaves the summary sentence to the conversation', () => {
    render(
      <LeadList run={run} rows={[{ ...row, effective_date: null }]} selected={QUEUE} onSelect={() => undefined} />,
    )
    expect(screen.getByText(/No effective date · /)).toBeInTheDocument()
    expect(screen.queryByText(/follow-ups sent/)).toBeNull()
  })

  it('says "no address" for a lead whose label is its id', () => {
    render(<LeadList run={run} rows={rows} selected={QUEUE} onSelect={() => undefined} />)
    expect(screen.getByRole('button', { name: /Lead 001/ })).toHaveTextContent('no address')
    expect(screen.getByRole('button', { name: 'Queue' })).toHaveAttribute('aria-current', 'true')
  })

  it('reports the lead id of a clicked lead and the queue key of the Queue entry', async () => {
    const onSelect = vi.fn()
    render(<LeadList run={run} rows={rows} selected={QUEUE} onSelect={onSelect} />)
    await userEvent.click(screen.getByRole('button', { name: /Lead 009/ }))
    await userEvent.click(screen.getByRole('button', { name: 'Queue' }))
    expect(onSelect.mock.calls).toEqual([['LEAD-00000042-009'], [QUEUE]])
  })

  it('points to the demo controls when no run is loaded', () => {
    render(
      <LeadList run={{ ...run, run_id: null }} rows={[]} selected={QUEUE} onSelect={() => undefined} />,
    )
    expect(screen.getByText('No leads are loaded. Use Demo controls, bottom right.')).toBeInTheDocument()
  })
})
