// ABOUTME: The drill-down panel's views: a fact with its observations, the lead's timeline with the cited event expanded in place, a message or reply, and a playbook page.
// ABOUTME: Each view reads the lead and its events as loaded; a target the lead does not hold shows one line saying so.
import { useEffect, useRef } from 'react'
import type { components } from '@/api/types'
import { Badge } from '@/components/ui/badge'
import { fieldLabel, formatFieldValue, formatTime, labelKeys } from '@/format'
import { ACTOR_LABELS, DRAFT_STATE_LABELS, EVENT_LABELS, MESSAGE_KIND_LABELS, SOURCE_LABELS } from '@/labels'
import type { PanelTarget } from '@/surface'
import { effectLine } from './effectLine'

type Schemas = components['schemas']
type EventRow = Schemas['EventRow']

export type ViewProps = {
  target: Exclude<PanelTarget, { kind: 'lead' }>
  lead: Schemas['LeadDetail']
  events: EventRow[]
  onOpen: (target: PanelTarget) => void
}

function NotFound() {
  return <p className="text-sm text-muted-foreground">Not found.</p>
}

function Heading({ children }: { children: React.ReactNode }) {
  return <h3 className="text-base font-medium">{children}</h3>
}

function OpenLink({ onClick, children }: { onClick: () => void; children: React.ReactNode }) {
  return (
    <button type="button" onClick={onClick} className="text-left text-sm underline">
      {children}
    </button>
  )
}

function openEvent({ target, onOpen }: ViewProps, event: EventRow) {
  onOpen({ kind: 'event', lead_id: target.lead_id, id: event.id })
}

// One event of the timeline: a row that selects it, and, when selected, its details in place.
function TimelineEvent({ event, selected, lead, onSelect }: { event: EventRow; selected: boolean; lead: Schemas['LeadDetail']; onSelect: () => void }) {
  const row = useRef<HTMLLIElement>(null)
  useEffect(() => {
    if (selected) row.current?.scrollIntoView({ block: 'center' })
  }, [selected])
  return (
    <li ref={row} className="relative pl-5" aria-current={selected ? 'true' : undefined}>
      <span
        aria-hidden="true"
        className={`absolute top-1.5 left-0 h-2.5 w-2.5 rounded-full ${selected ? 'bg-accent' : 'bg-border-strong'}`}
      />
      {selected ? (
        <div className="flex flex-col gap-2 rounded-md border bg-soft p-3">
          <p className="font-medium">{labelKeys(event.summary, lead.fields)}</p>
          <p className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <Badge variant="secondary">{EVENT_LABELS[event.type]}</Badge>
            <span>{`${ACTOR_LABELS[event.actor]}, ${formatTime(event.sim_ts)}`}</span>
          </p>
          {event.fact_key !== null && <p className="text-xs text-muted-foreground">{`Field: ${fieldLabel(lead.fields, event.fact_key)} (${event.fact_key})`}</p>}
          {event.lookup !== null && (
            <p className="text-xs text-muted-foreground">
              {event.lookup.missing_inputs.length > 0
                ? `Lookup ${event.lookup.status.replace('_', ' ')}; missing ${event.lookup.missing_inputs.map((key) => fieldLabel(lead.fields, key)).join(', ')}`
                : `Lookup ${event.lookup.status.replace('_', ' ')}`}
            </p>
          )}
          {event.message !== null && (
            <div className="flex flex-col gap-1">
              {event.message.subject !== null && <p className="font-medium">{event.message.subject}</p>}
              <pre className="whitespace-pre-wrap break-words rounded-md bg-background p-3 font-sans">{event.message.body}</pre>
            </div>
          )}
        </div>
      ) : (
        <button type="button" onClick={onSelect} className="flex w-full flex-col items-start gap-0.5 text-left hover:underline">
          <span className="text-xs text-muted-foreground">{`${formatTime(event.sim_ts)} · ${EVENT_LABELS[event.type]}`}</span>
          <span className="line-clamp-1">{labelKeys(event.summary, lead.fields)}</span>
        </button>
      )}
    </li>
  )
}

// The lead's timeline, oldest first, with the cited event expanded in place; a click on another row moves the expansion.
export function EventView(props: ViewProps) {
  const { events, lead } = props
  if (!events.some((event) => String(event.id) === String(props.target.id))) return <NotFound />
  return (
    // The rows are one line each, so the timeline reads at a column's width rather than stretching the panel to its maximum.
    <ol aria-label="Timeline" className="flex w-[540px] flex-col gap-3 border-l border-border-strong pl-0 text-sm [&>li]:-ml-[5px]">
      {events.map((event) => (
        <TimelineEvent
          key={event.id}
          event={event}
          selected={String(event.id) === String(props.target.id)}
          lead={lead}
          onSelect={() => openEvent(props, event)}
        />
      ))}
    </ol>
  )
}

export function FactView(props: ViewProps) {
  const { lead, events } = props
  const recorded = events.find((event) => String(event.id) === String(props.target.id))
  const key = recorded?.fact_key
  const fact = lead.facts.find((candidate) => candidate.key === key)
  if (key === null || key === undefined || fact === undefined) return <NotFound />
  const source = events.find((event) => event.id === fact.event_id)
  const observations = events.filter((event) => event.type === 'fact_observed' && event.fact_key === key)
  return (
    <div className="flex flex-col gap-4 text-sm">
      <section aria-label="Value in use" className="flex flex-col gap-1">
        <p>
          {fieldLabel(lead.fields, key)} <span className="font-mono text-xs text-muted-foreground">{key}</span>
        </p>
        <p>{formatFieldValue(lead.fields, key, fact.value)}</p>
        <p className="flex flex-wrap items-center gap-2">
          <Badge variant="secondary">{SOURCE_LABELS[fact.source]}</Badge>
          {source !== undefined && <span>{`Observed ${formatTime(source.sim_ts)}`}</span>}
        </p>
        {source !== undefined && <OpenLink onClick={() => openEvent(props, source)}>{`Recorded ${formatTime(source.sim_ts)}`}</OpenLink>}
      </section>
      <section aria-label="Observations" className="flex flex-col gap-2">
        <Heading>Observations</Heading>
        <ul className="flex flex-col gap-2">
          {observations.map((event) => (
            <li key={event.id} className="flex flex-col">
              <span className="text-muted-foreground">{formatTime(event.sim_ts)}</span>
              <OpenLink onClick={() => openEvent(props, event)}>{event.summary}</OpenLink>
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}

export function MessageView({ target, lead }: ViewProps) {
  const draft = lead.drafts.find((candidate) => candidate.intent_id === String(target.id))
  if (draft === undefined) return <NotFound />
  return (
    <div className="flex flex-col gap-2 text-sm">
      <Heading>Message (current)</Heading>
      <p className="flex flex-wrap items-center gap-2">
        <Badge variant="secondary">{MESSAGE_KIND_LABELS[draft.kind]}</Badge>
        <Badge variant="outline">{DRAFT_STATE_LABELS[draft.state]}</Badge>
        <span>{`To ${draft.recipient}`}</span>
      </p>
      <p className="font-medium">{draft.subject}</p>
      <pre className="whitespace-pre-wrap break-words rounded-md bg-muted p-3 font-sans">{draft.body}</pre>
    </div>
  )
}

export function ReplyView({ target, events }: ViewProps) {
  const reply = events.find((event) => String(event.id) === String(target.id))
  if (reply === undefined || reply.message === null) return <NotFound />
  return (
    <div className="flex flex-col gap-2 text-sm">
      <Heading>From the producer</Heading>
      <p className="text-muted-foreground">{formatTime(reply.sim_ts)}</p>
      <pre className="whitespace-pre-wrap break-words rounded-md bg-muted p-3 font-sans">{reply.message.body}</pre>
    </div>
  )
}

export function PageView({ target, lead }: ViewProps) {
  const page = lead.pages.find((candidate) => candidate.key === String(target.id))
  if (page === undefined) return <NotFound />
  return (
    <div className="flex flex-col gap-4 text-sm">
      <Heading>{`${page.key} (current)`}</Heading>
      <ul aria-label="Page effects" className="flex flex-col gap-2">
        {page.effects.map((planned) => (
          <li key={`${planned.effect.type}-${planned.effect.rule}`}>
            <p>
              {effectLine(planned.effect)}
              {!planned.committed && ' - not committed'}
            </p>
            <p className="font-mono text-muted-foreground">{planned.trace.board_path.join(' > ')}</p>
          </li>
        ))}
      </ul>
      {page.declines_on_every_branch.map((decline, index) => (
        <div key={index} className="flex flex-col gap-1">
          <p>Declines on every branch</p>
          <ul className="font-mono text-muted-foreground">
            {decline.alternatives.map((branch) => (
              <li key={branch.rule}>{`${branch.rule}: ${branch.board_path.join(' > ')}`}</li>
            ))}
          </ul>
        </div>
      ))}
      {page.waits_on.length > 0 && <p>{`Waits on ${page.waits_on.join(', ')}`}</p>}
      {page.not_evaluated.map((note) => (
        <p key={note.ref}>{note.text}</p>
      ))}
    </div>
  )
}
