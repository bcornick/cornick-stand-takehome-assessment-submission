// ABOUTME: Tests the lead detail pane against the ui fixtures: next action, facts with source tags, playbook checklist and its toggle.
// ABOUTME: Also the draft, the notes, the read-only blockers and choices, the links, and that no confidence is shown.
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { pageLabel } from '@/labels'
import { detail, details } from '@/test/fixtures'
import { DetailPane } from './DetailPane'

function renderLead(leadId: string) {
  const lead = detail(leadId)
  const view = render(<DetailPane lead={lead} />)
  return { lead, ...view }
}

function playbookItems() {
  // One item per page; the effect lists nested in an item are not pages.
  return Array.from(screen.getByRole('list', { name: 'Playbook path' }).children) as HTMLElement[]
}

function factRow(key: string) {
  return within(screen.getByRole('table', { name: 'Facts' })).getByRole('row', {
    name: new RegExp(`^${key} `),
  })
}

describe('DetailPane', () => {
  it('shows the next action', () => {
    const { lead } = renderLead('LEAD-00000042-003')
    const section = screen.getByRole('region', { name: 'Next action' })
    expect(within(section).getByText(lead.next_action!)).toBeInTheDocument()
  })

  it('lists every fact with its source tag, p_f among them', () => {
    const { lead } = renderLead('LEAD-00000042-003')
    const rows = within(screen.getByRole('table', { name: 'Facts' })).getAllByRole('row')
    expect(rows).toHaveLength(lead.facts.length + 1)
    const pf = factRow('p_f')
    expect(within(pf).getByText('0.79')).toBeInTheDocument()
    expect(within(pf).getByText('Fetched')).toBeInTheDocument()
    const street = factRow('street_address')
    expect(within(street).getByText('9273 Hillside Ct')).toBeInTheDocument()
    expect(within(street).getByText('Submitted')).toBeInTheDocument()
  })

  it('shows a derived fact and an assumed fact with their tags', () => {
    const lead = detail('LEAD-00000042-000')
    const assumed = lead.facts.find((fact) => fact.source === 'assumed')!
    renderLead('LEAD-00000042-000')
    const row = factRow(assumed.key)
    expect(within(row).getByText('Assumed')).toBeInTheDocument()
    expect(within(row).getByText(String(assumed.value))).toBeInTheDocument()
    const derived = lead.facts.find((fact) => fact.source === 'derived')!
    expect(
      within(factRow(derived.key)).getByText('Derived'),
    ).toBeInTheDocument()
  })

  it('shows a stub fact as a stub', () => {
    const lead = detail('LEAD-00000042-009')
    const stub = lead.facts.find((fact) => fact.is_stub)!
    expect(stub.key).toBe('p_f')
    renderLead('LEAD-00000042-009')
    const row = factRow('p_f')
    expect(within(row).getByText('Stub')).toBeInTheDocument()
    const other = factRow('street_address')
    expect(within(other).queryByText('Stub')).not.toBeInTheDocument()
  })

  it('shows a pending observation as pending review', () => {
    const lead = structuredClone(detail('LEAD-00000042-003'))
    lead.facts = lead.facts.map((fact) =>
      fact.key === 'p_f' ? { ...fact, status: 'pending_review' as const } : fact,
    )
    render(<DetailPane lead={lead} />)
    expect(within(factRow('p_f')).getByText('Pending review')).toBeInTheDocument()
    expect(within(factRow('county')).queryByText('Pending review')).toBeNull()
  })

  it('lists the playbook path as a checklist, one line per page', () => {
    const { lead } = renderLead('LEAD-00000042-003')
    expect(lead.playbook).toHaveLength(12)
    const items = playbookItems()
    expect(items).toHaveLength(12)
    const fire = items[lead.playbook.findIndex((page) => page.graph === 'fire_simulation')]!
    expect(within(fire).getByText('Fire simulation')).toBeInTheDocument()
    expect(within(fire).getByText('Applies')).toBeInTheDocument()
    expect(within(fire).getByText('Undecided')).toBeInTheDocument()
    expect(within(fire).getByText(/I13\.fire_fail/)).toBeInTheDocument()
    expect(within(fire).getByText(/Decline/)).toBeInTheDocument()
    expect(within(fire).getByText(/04:D_FAIL/)).toBeInTheDocument()
    const plumbing = items[lead.playbook.findIndex((page) => page.graph === 'plumbing')]!
    expect(within(plumbing).getByText('Not evaluated')).toBeInTheDocument()
  })

  it('shows only the exception pages when the exceptions-only toggle is on', async () => {
    const { lead } = renderLead('LEAD-00000042-003')
    const exceptions = lead.playbook.filter((page) => page.exception)
    expect(exceptions.length).toBeGreaterThan(0)
    expect(exceptions.length).toBeLessThan(lead.playbook.length)
    const toggle = screen.getByRole('switch', { name: 'Exceptions only' })
    expect(toggle).not.toBeChecked()
    await userEvent.click(toggle)
    expect(toggle).toBeChecked()
    const items = playbookItems()
    expect(items).toHaveLength(exceptions.length)
    const shown = items.map((item) => within(item).getByRole('heading', { level: 4 }).textContent)
    expect(shown).toEqual(exceptions.map((page) => pageLabel(page.graph)))
    await userEvent.click(toggle)
    expect(playbookItems()).toHaveLength(12)
  })

  it('shows the draft with its kind, recipient, subject, body, state and round', () => {
    const { lead } = renderLead('LEAD-00000042-000')
    const draft = lead.drafts[0]!
    const section = screen.getByRole('region', { name: 'Drafts' })
    expect(within(section).getByText('Decline notice')).toBeInTheDocument()
    expect(within(section).getByText(draft.recipient)).toBeInTheDocument()
    expect(within(section).getByText(draft.subject)).toBeInTheDocument()
    expect(within(section).getByText('Draft')).toBeInTheDocument()
    expect(within(section).getByText('Round 1')).toBeInTheDocument()
    expect(
      within(section).getByText((_, element) => element?.tagName === 'PRE' && element.textContent === draft.body),
    ).toBeInTheDocument()
  })

  it('shows a sent request as sent', () => {
    renderLead('LEAD-00000042-003')
    const section = screen.getByRole('region', { name: 'Drafts' })
    expect(within(section).getByText('Routine request')).toBeInTheDocument()
    expect(within(section).getByText('Sent')).toBeInTheDocument()
  })

  it('shows the non-blocking notes', () => {
    const { lead } = renderLead('LEAD-00000042-003')
    expect(lead.notes.length).toBeGreaterThan(0)
    const section = screen.getByRole('region', { name: 'Notes' })
    for (const note of lead.notes) {
      expect(within(section).getByText(note.text)).toBeInTheDocument()
    }
  })

  it('shows open blockers and open choices read-only, with their shown values', () => {
    const { lead } = renderLead('LEAD-00000042-003')
    const blockers = screen.getByRole('region', { name: 'Open blockers' })
    for (const blocker of lead.blockers) {
      expect(within(blockers).getByText(blocker.detail.text)).toBeInTheDocument()
    }
    expect(within(blockers).getByText('Underwriter question')).toBeInTheDocument()
    expect(within(blockers).getByText('Producer reply')).toBeInTheDocument()
    const choices = screen.getByRole('region', { name: 'Open choices' })
    const choice = lead.open_choices[0]!
    expect(within(choices).getByText(choice.prompt)).toBeInTheDocument()
    for (const option of choice.options) {
      expect(within(choices).getByText(option)).toBeInTheDocument()
    }
    const pf = within(choices).getByRole('row', { name: /^p_f / })
    expect(within(pf).getByText('0.79')).toBeInTheDocument()
    expect(within(choices).getByText('Too Close')).toBeInTheDocument()
  })

  it('offers no action buttons', () => {
    renderLead('LEAD-00000042-000')
    expect(screen.queryAllByRole('button')).toHaveLength(0)
  })

  it('links to the search and map pages', () => {
    const { lead } = renderLead('LEAD-00000042-003')
    const section = screen.getByRole('region', { name: 'Links' })
    for (const link of lead.links) {
      const anchor = within(section).getByRole('link', { name: link.label })
      expect(anchor).toHaveAttribute('href', link.url)
      expect(anchor).toHaveAttribute('target', '_blank')
    }
  })

  it.each(Object.keys(details))('shows no model confidence for %s', (leadId) => {
    const { container } = renderLead(leadId)
    expect(container.textContent).not.toMatch(/confidence/i)
  })
})
