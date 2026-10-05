// ABOUTME: The lead detail pane: next action, facts with source tags, playbook checklist, drafts, notes, blockers, choices and links.
// ABOUTME: Read-only; it renders one LeadDetail and shows no model confidence.
import { useState } from 'react'
import type { components } from '@/api/types'
import { Badge } from '@/components/ui/badge'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
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
  APPLIES_LABELS,
  BLOCKER_KIND_LABELS,
  DRAFT_STATE_LABELS,
  EFFECT_LABELS,
  MESSAGE_KIND_LABELS,
  OWNER_LABELS,
  pageLabel,
  RESULT_LABELS,
  SOURCE_LABELS,
  STATUS_LABELS,
} from '@/labels'

type Schemas = components['schemas']
type LeadDetail = Schemas['LeadDetail']

export function DetailPane({ lead }: { lead: LeadDetail }) {
  return (
    <article className="flex flex-col gap-6">
      <header className="flex flex-wrap items-center gap-2">
        <h2 className="font-mono text-xl font-semibold">{lead.lead_id}</h2>
        <Badge variant="secondary">{STATUS_LABELS[lead.status]}</Badge>
      </header>
      <Section title="Next action">
        <p>{lead.next_action ?? 'No further action.'}</p>
      </Section>
      <Section title="Open blockers">
        <Blockers blockers={lead.blockers} />
      </Section>
      <Section title="Open choices">
        <Choices choices={lead.open_choices} />
      </Section>
      <Section title="Playbook path">
        <Playbook pages={lead.playbook} />
      </Section>
      <Section title="Facts">
        <Facts facts={lead.facts} />
      </Section>
      <Section title="Drafts">
        <Drafts drafts={lead.drafts} />
      </Section>
      <Section title="Notes">
        <Notes notes={lead.notes} />
      </Section>
      <Section title="Links">
        <Links links={lead.links} />
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

function Blockers({ blockers }: { blockers: LeadDetail['blockers'] }) {
  if (blockers.length === 0) return <Empty>No open blockers.</Empty>
  return (
    <ul className="flex flex-col gap-2">
      {blockers.map((blocker) => (
        <li key={blocker.item_id} className="flex flex-wrap items-baseline gap-2">
          <Badge variant="outline">{BLOCKER_KIND_LABELS[blocker.kind]}</Badge>
          <span className="text-sm text-muted-foreground">
            {`Waits on ${OWNER_LABELS[blocker.owner].toLowerCase()}`}
          </span>
          <span>{blocker.detail.text}</span>
        </li>
      ))}
    </ul>
  )
}

function Choices({ choices }: { choices: LeadDetail['open_choices'] }) {
  if (choices.length === 0) return <Empty>No open choices.</Empty>
  return (
    <ul className="flex flex-col gap-4">
      {choices.map((choice) => (
        <li key={choice.choice_id} className="flex flex-col gap-2">
          <p className="font-mono text-sm">{choice.choice_id}</p>
          <p>{choice.prompt}</p>
          <p className="flex flex-wrap items-center gap-2 text-sm">
            <span>Options:</span>
            {choice.options.map((option) => (
              <Badge key={option} variant="outline" className="font-mono">
                {option}
              </Badge>
            ))}
          </p>
          <Table aria-label={`Values shown with ${choice.choice_id}`}>
            <TableHeader>
              <TableRow>
                <TableHead>Field</TableHead>
                <TableHead>Value</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {choice.show.map((field) => (
                <TableRow key={field}>
                  <TableCell className="font-mono">{field}</TableCell>
                  <TableCell>{formatValue(choice.shown_values[field])}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </li>
      ))}
    </ul>
  )
}

function Playbook({ pages }: { pages: LeadDetail['playbook'] }) {
  const [exceptionsOnly, setExceptionsOnly] = useState(false)
  const shown = exceptionsOnly ? pages.filter((page) => page.exception) : pages
  return (
    <>
      <Label className="flex items-center gap-2">
        <Switch checked={exceptionsOnly} onCheckedChange={setExceptionsOnly} />
        Exceptions only
      </Label>
      <ul aria-label="Playbook path" className="flex flex-col gap-3">
        {shown.map((page) => (
          <li key={page.graph} className="flex flex-col gap-1 rounded-md border p-3">
            <h4 className="font-medium">{pageLabel(page.graph)}</h4>
            <p className="flex flex-wrap items-center gap-2 text-sm">
              <Badge variant="outline">{APPLIES_LABELS[page.applies]}</Badge>
              {page.result !== null && <Badge variant="secondary">{RESULT_LABELS[page.result]}</Badge>}
              {page.exception && <Badge variant="destructive">Exception</Badge>}
            </p>
            {page.waits_on.length > 0 && (
              <p className="text-sm">{`Waits on: ${page.waits_on.join(', ')}`}</p>
            )}
            {page.effects.length > 0 && (
              <ul className="text-sm">
                {page.effects.map((planned) => (
                  <li key={planned.effect.rule}>
                    {`${EFFECT_LABELS[planned.effect.type]} (${planned.effect.rule})`}
                    {'text' in planned.effect && `: ${planned.effect.text}`}
                    {!planned.committed && ' - not committed'}
                  </li>
                ))}
              </ul>
            )}
          </li>
        ))}
      </ul>
    </>
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
              {fact.is_stub && <Badge variant="outline">Stub</Badge>}
              {fact.status === 'pending_review' && <Badge variant="outline">Pending review</Badge>}
              {fact.status === 'rejected' && <Badge variant="outline">Rejected</Badge>}
              {fact.confirmed && <Badge variant="outline">Confirmed</Badge>}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}

function Drafts({ drafts }: { drafts: LeadDetail['drafts'] }) {
  if (drafts.length === 0) return <Empty>No drafts.</Empty>
  return (
    <ul className="flex flex-col gap-4">
      {drafts.map((draft) => (
        <li key={draft.intent_id} className="flex flex-col gap-2 rounded-md border p-3">
          <p className="flex flex-wrap items-center gap-2 text-sm">
            <Badge variant="secondary">{MESSAGE_KIND_LABELS[draft.kind]}</Badge>
            <Badge variant="outline">{DRAFT_STATE_LABELS[draft.state]}</Badge>
            <span>{`Round ${draft.round}`}</span>
          </p>
          <dl className="grid grid-cols-[auto_1fr] gap-x-3 text-sm">
            <dt className="text-muted-foreground">To</dt>
            <dd>{draft.recipient}</dd>
            <dt className="text-muted-foreground">Subject</dt>
            <dd>{draft.subject}</dd>
          </dl>
          <pre className="whitespace-pre-wrap rounded-md bg-muted p-3 font-sans text-sm">{draft.body}</pre>
        </li>
      ))}
    </ul>
  )
}

function Notes({ notes }: { notes: LeadDetail['notes'] }) {
  if (notes.length === 0) return <Empty>No notes.</Empty>
  return (
    <ul className="list-disc pl-5 text-sm">
      {notes.map((note) => (
        <li key={`${note.kind}-${note.ref}`}>{note.text}</li>
      ))}
    </ul>
  )
}

function Links({ links }: { links: LeadDetail['links'] }) {
  if (links.length === 0) return <Empty>No links.</Empty>
  return (
    <ul className="list-disc pl-5 text-sm">
      {links.map((link) => (
        <li key={link.url}>
          <a href={link.url} target="_blank" rel="noreferrer" className="underline underline-offset-2">
            {link.label}
          </a>
        </li>
      ))}
    </ul>
  )
}
