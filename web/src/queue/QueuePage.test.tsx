// ABOUTME: Tests the queue page against the ui fixtures: row order, group boundaries, the six-count summary and the mode label.
// ABOUTME: Row order is the order received; the page never re-sorts.
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { rows, run } from '@/test/fixtures'
import { QueuePage } from './QueuePage'

function renderQueue(overrides: Partial<Parameters<typeof QueuePage>[0]> = {}) {
  const onSelect = vi.fn()
  render(<QueuePage run={run} rows={rows} selectedLeadId={null} onSelect={onSelect} {...overrides} />)
  return { onSelect }
}

function renderedLeadIds(): string[] {
  return screen
    .getAllByRole('row')
    .filter((row) => within(row).queryByRole('button') !== null)
    .map((row) => within(row).getByRole('button').textContent ?? '')
}

describe('QueuePage', () => {
  it('lists the ten leads in the order received', () => {
    renderQueue()
    expect(rows).toHaveLength(10)
    expect(renderedLeadIds()).toEqual(rows.map((row) => row.lead_id))
  })

  it('does not re-sort rows it is given', () => {
    const swapped = [rows[1]!, rows[0]!, ...rows.slice(2)]
    renderQueue({ rows: swapped })
    expect(renderedLeadIds()).toEqual(swapped.map((row) => row.lead_id))
  })

  it('puts a heading and a table before each group present, with no empty group', () => {
    renderQueue()
    const headings = screen.getAllByRole('heading', { level: 2 }).map((h) => h.textContent)
    expect(headings).toEqual(['Blocked on the underwriter', 'Waiting on data or producer'])
    const tables = screen.getAllByRole('table')
    expect(tables.map((table) => within(table).getAllByRole('button').length)).toEqual([3, 7])
    const idsByTable = tables.map((table) =>
      within(table)
        .getAllByRole('button')
        .map((b) => b.textContent),
    )
    expect(idsByTable).toEqual([
      rows.filter((row) => row.group === 'blocked_on_underwriter').map((row) => row.lead_id),
      rows.filter((row) => row.group === 'waiting_on_data_or_producer').map((row) => row.lead_id),
    ])
    expect(screen.queryByRole('heading', { name: 'Finished' })).not.toBeInTheDocument()
  })

  it('shows a finished group when a row is finished', () => {
    const finished = { ...rows[9]!, status: 'declined' as const, group: 'finished' as const }
    renderQueue({ rows: [...rows.slice(0, 9), finished] })
    expect(screen.getByRole('heading', { name: 'Finished' })).toBeInTheDocument()
  })

  it('heads the page with one sentence holding all six counts, zeros included', () => {
    renderQueue()
    const s = run.summary
    expect(s.quotes_sent).toBe(0)
    expect(
      screen.getByText(
        `${s.quotes_sent} quotes sent, ${s.follow_ups_sent} follow-ups sent, ` +
          `${s.declines_approved} declines approved, ${s.waiting_on_underwriter} waiting on the underwriter, ` +
          `${s.waiting_on_data} waiting on data, ${s.delivery_unknown} delivery unknown.`,
      ),
    ).toBeInTheDocument()
  })

  it('shows the mode and the run id', () => {
    renderQueue()
    expect(screen.getByText(`Mode: ${run.mode}`)).toBeInTheDocument()
    expect(screen.getByText(`Run ${run.run_id}`)).toBeInTheDocument()
  })

  it('shows a row with its status, next action, owner, age, effective date and ask count', () => {
    renderQueue()
    const row = screen.getByRole('button', { name: 'LEAD-00000042-003' }).closest('tr')!
    const cells = within(row)
    expect(cells.getByText('In progress')).toBeInTheDocument()
    expect(cells.getByText('Underwriter question')).toBeInTheDocument()
    expect(cells.getByText('Underwriter')).toBeInTheDocument()
    expect(cells.getByText('1.97 days')).toBeInTheDocument()
    expect(cells.getByText('2026-07-21')).toBeInTheDocument()
    expect(cells.getByText('13')).toBeInTheDocument()
  })

  it('labels the age column as an assumed service level and marks each breached row', () => {
    renderQueue()
    expect(screen.getAllByText(/assumed two-business-day service level/).length).toBeGreaterThan(0)
    const breached = rows.filter((row) => row.service_level_breached).map((row) => row.lead_id)
    expect(breached.length).toBeGreaterThan(0)
    expect(breached.length).toBeLessThan(rows.length)
    const marked = screen
      .getAllByRole('row')
      .filter((row) => within(row).queryByText('Past service level') !== null)
      .map((row) => within(row).getByRole('button').textContent)
    expect(marked).toEqual(breached)
  })

  it('opens a lead when its row is selected', async () => {
    const { onSelect } = renderQueue()
    await userEvent.click(screen.getByRole('button', { name: 'LEAD-00000042-000' }))
    expect(onSelect).toHaveBeenCalledExactlyOnceWith('LEAD-00000042-000')
  })

  it('marks the selected row', () => {
    renderQueue({ selectedLeadId: 'LEAD-00000042-006' })
    expect(screen.getByRole('button', { name: 'LEAD-00000042-006' })).toHaveAttribute('aria-current', 'true')
    expect(screen.getByRole('button', { name: 'LEAD-00000042-003' })).not.toHaveAttribute('aria-current')
  })
})
