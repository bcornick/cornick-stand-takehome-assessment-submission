// ABOUTME: The full lead view of the drill-down panel: what the lead waits on, its facts with source tags, plan and messages, and the actions on the whole lead.
// ABOUTME: Shows one LeadDetail; the plan is the internal view, so rule ids appear here and never in a message.
import { Fragment } from 'react'
import type { components } from '@/api/types'
import { Badge } from '@/components/ui/badge'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { fieldLabel, formatFieldValue, shortLeadId } from '@/format'
import {
  BLOCKER_KIND_LABELS,
  DRAFT_STATE_LABELS,
  MISSING_LABELS,
  MESSAGE_KIND_LABELS,
  SOURCE_LABELS,
  STATUS_LABELS,
} from '@/labels'
import { effectLine } from '@/panel/effectLine'
import { LeadActions } from './LeadActions'

type Schemas = components['schemas']
type LeadDetail = Schemas['LeadDetail']
type Plan = Schemas['ActionPlan']

type Props = { lead: LeadDetail; onChange: () => void }

export function DetailPane({ lead, onChange }: Props) {
  return (
    <article className="flex flex-col gap-6">
      <header className="flex flex-col gap-1">
        <h2 className="font-mono text-xl font-semibold">{shortLeadId(lead.lead_id)}</h2>
        <p className="flex flex-wrap items-center gap-2 text-sm">
          <Badge variant="secondary">{STATUS_LABELS[lead.status]}</Badge>
          <span>{lead.label}</span>
        </p>
      </header>
      <Section title="Waiting on">
        <Blockers blockers={lead.blockers} />
      </Section>
      <Section title="Facts">
        <Facts facts={lead.facts} fields={lead.fields} missing={lead.missing_fields} />
      </Section>
      <Section title="Plan">
        {lead.plan === null ? <Empty>Not triaged yet.</Empty> : <PlanView plan={lead.plan} />}
      </Section>
      <Section title="Messages">
        <Drafts drafts={lead.drafts} />
      </Section>
      <Section title="Lead actions">
        <LeadActions lead={lead} onChange={onChange} />
      </Section>
    </article>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  const headingId = `section-${title.toLowerCase().replace(/\s+/g, '-')}`
  return (
    <section aria-labelledby={headingId} className="flex flex-col gap-2">
      <h3 id={headingId} className="text-base font-medium">
        {title}
      </h3>
      {children}
    </section>
  )
}

function Empty({ children }: { children: string }) {
  return <p className="text-sm text-muted-foreground">{children}</p>
}

function Drafts({ drafts }: { drafts: LeadDetail['drafts'] }) {
  if (drafts.length === 0) return <Empty>No messages.</Empty>
  return (
    <ul className="flex flex-col gap-4">
      {drafts.map((draft) => (
        <li key={draft.intent_id} className="flex flex-col gap-2 rounded-md border p-3">
          <p className="flex flex-wrap items-center gap-2 text-sm">
            <Badge variant="secondary">{MESSAGE_KIND_LABELS[draft.kind]}</Badge>
            <Badge variant="outline">{DRAFT_STATE_LABELS[draft.state]}</Badge>
            <span>{`To ${draft.recipient}`}</span>
          </p>
          <p className="text-sm font-medium">{draft.subject}</p>
          <pre className="whitespace-pre-wrap break-words rounded-md bg-muted p-3 font-sans text-sm">{draft.body}</pre>
        </li>
      ))}
    </ul>
  )
}

function Blockers({ blockers }: { blockers: LeadDetail['blockers'] }) {
  if (blockers.length === 0) return <Empty>Nothing is waiting.</Empty>
  return (
    <ul className="flex flex-col gap-2 text-sm">
      {blockers.map((blocker) => (
        <li key={blocker.item_id} className="flex flex-wrap items-baseline gap-2">
          {/* The kind names who the item waits on; its colour marks one that needs the underwriter. */}
          <Badge variant={blocker.owner === 'underwriter' ? 'needs' : 'waiting'}>{BLOCKER_KIND_LABELS[blocker.kind]}</Badge>
          <span>{blocker.detail.text}</span>
        </li>
      ))}
    </ul>
  )
}

function PlanView({ plan }: { plan: Plan }) {
  return (
    <div className="flex flex-col gap-2 text-sm">
      <ul aria-label="Plan effects" className="flex flex-col gap-1">
        {plan.effects.map((planned) => (
          <li key={`${planned.effect.type}-${planned.effect.rule}`}>
            {effectLine(planned.effect)}
            {!planned.committed && ' - not committed'}
          </li>
        ))}
      </ul>
      {plan.undecided.map((page) => (
        <p key={page.graph}>{`${page.graph} is undecided: it waits on ${page.waits_on.join(', ')}.`}</p>
      ))}
      {plan.open_choices.map((choice) => (
        <p key={choice.choice_id}>{`Open choice ${choice.choice_id}: ${choice.prompt}`}</p>
      ))}
      {plan.not_evaluated.map((note) => (
        <p key={note.ref}>{note.text}</p>
      ))}
    </div>
  )
}

// The facts grouped under the registry's sections, sections and rows in registry order.
function factsBySection(facts: LeadDetail['facts'], fields: LeadDetail['fields']) {
  const sections = new Map<string, LeadDetail['facts']>()
  for (const field of fields) {
    const inField = facts.filter((fact) => fact.key === field.key)
    if (inField.length > 0) sections.set(field.section, [...(sections.get(field.section) ?? []), ...inField])
  }
  return sections
}

// The missing fields under the heading of how each is resolved, headings in the order first met.
function missingByHeading(missing: LeadDetail['missing_fields']) {
  const headings = new Map<string, string[]>()
  for (const { key, resolution } of missing) {
    const heading = MISSING_LABELS[resolution]
    headings.set(heading, [...(headings.get(heading) ?? []), key])
  }
  return headings
}

function Facts({
  facts,
  fields,
  missing,
}: {
  facts: LeadDetail['facts']
  fields: LeadDetail['fields']
  missing: LeadDetail['missing_fields']
}) {
  return (
    <>
      {missing.length > 0 && (
        <section aria-label="Missing" className="flex flex-col gap-2 text-sm">
          <h4 className="font-medium">Missing</h4>
          {[...missingByHeading(missing)].map(([heading, keys]) => (
            <div key={heading} className="flex flex-col gap-1">
              <h5 className="text-muted-foreground">{heading}</h5>
              <ul aria-label={heading} className="list-disc pl-5">
                {keys.map((key) => (
                  <li key={key}>{fieldLabel(fields, key)}</li>
                ))}
              </ul>
            </div>
          ))}
        </section>
      )}
      <Table aria-label="Facts" className="table-fixed">
        <TableHeader>
          <TableRow>
            <TableHead>Field</TableHead>
            <TableHead>Value</TableHead>
            <TableHead>Source</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {[...factsBySection(facts, fields)].map(([section, inSection]) => (
            <Fragment key={section}>
              <TableRow>
                <TableCell colSpan={3} className="bg-muted font-medium">
                  {section}
                </TableCell>
              </TableRow>
              {inSection.map((fact) => (
                <TableRow key={fact.observation_id}>
                  <TableCell className="whitespace-normal break-words">{fieldLabel(fields, fact.key)}</TableCell>
                  <TableCell className="whitespace-normal break-words">
                    {formatFieldValue(fields, fact.key, fact.value)}
                  </TableCell>
                  <TableCell className="space-x-1 whitespace-normal">
                    {fact.source !== 'submitted' && <Badge variant="secondary">{SOURCE_LABELS[fact.source]}</Badge>}
                    {fact.status === 'pending_review' && <Badge variant="outline">Pending review</Badge>}
                    {fact.confirmed && <Badge variant="outline">Confirmed</Badge>}
                  </TableCell>
                </TableRow>
              ))}
            </Fragment>
          ))}
        </TableBody>
      </Table>
    </>
  )
}
