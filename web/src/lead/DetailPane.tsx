// ABOUTME: The lead detail pane: what the lead waits on with the actions of each item, the actions on the whole lead, its messages, plan, facts with source tags, and the events of what the system did.
// ABOUTME: Shows one LeadDetail; the plan is the internal view, so rule ids appear here and never in a message.
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
import { formatValue } from '@/format'
import {
  DRAFT_STATE_LABELS,
  EFFECT_LABELS,
  MESSAGE_KIND_LABELS,
  SOURCE_LABELS,
  STATUS_LABELS,
} from '@/labels'
import { EventList } from './EventList'
import { Blockers } from './ItemActions'
import { LeadActions } from './LeadActions'

type Schemas = components['schemas']
type LeadDetail = Schemas['LeadDetail']
type Plan = Schemas['ActionPlan']

type Props = { lead: LeadDetail; refresh: number; onChange: () => void }

export function DetailPane({ lead, refresh, onChange }: Props) {
  return (
    <article className="flex flex-col gap-6">
      <header className="flex flex-col gap-1">
        <h2 className="font-mono text-xl font-semibold">{lead.lead_id}</h2>
        <p className="flex flex-wrap items-center gap-2 text-sm">
          <Badge variant="secondary">{STATUS_LABELS[lead.status]}</Badge>
          <span>{lead.label}</span>
        </p>
      </header>
      <Section title="Waiting on">
        <Blockers lead={lead} onChange={onChange} />
      </Section>
      <Section title="Lead actions">
        <LeadActions lead={lead} onChange={onChange} />
      </Section>
      <Section title="Messages">
        <Drafts drafts={lead.drafts} />
      </Section>
      <Section title="Plan">
        {lead.plan === null ? <Empty>Not triaged yet.</Empty> : <PlanView plan={lead.plan} />}
      </Section>
      <Section title="Facts">
        <Facts facts={lead.facts} />
      </Section>
      <Section title="What the system did">
        <EventList leadId={lead.lead_id} refresh={refresh} />
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
          <pre className="whitespace-pre-wrap rounded-md bg-muted p-3 font-sans text-sm">{draft.body}</pre>
        </li>
      ))}
    </ul>
  )
}

function effectLine(effect: Plan['effects'][number]['effect']): string {
  const label = `${EFFECT_LABELS[effect.type]} (${effect.rule})`
  switch (effect.type) {
    case 'surcharge':
      return `${label}: ${effect.percent}%`
    case 'coverage_adjustment':
      return `${label}: ${effect.field} to ${effect.proposed_value}`
    case 'decline':
    case 'no_action':
      return label
    default:
      return `${label}: ${effect.text}`
  }
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

function Facts({ facts }: { facts: LeadDetail['facts'] }) {
  return (
    <Table aria-label="Facts">
      <TableHeader>
        <TableRow>
          <TableHead>Field</TableHead>
          <TableHead>Value</TableHead>
          <TableHead>Source</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {facts.map((fact) => (
          <TableRow key={fact.observation_id}>
            <TableCell className="font-mono">{fact.key}</TableCell>
            <TableCell>{formatValue(fact.value)}</TableCell>
            <TableCell className="space-x-1">
              <Badge variant="secondary">{SOURCE_LABELS[fact.source]}</Badge>
              {fact.status === 'pending_review' && <Badge variant="outline">Pending review</Badge>}
              {fact.confirmed && <Badge variant="outline">Confirmed</Badge>}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}
