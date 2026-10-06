// ABOUTME: The views of the drill-down panel, one per thing a citation or a link opens: an event, a fact with its observations, a message, a producer's reply and a playbook page.
// ABOUTME: Each view reads the lead and its events as loaded; a target the lead does not hold shows one line saying so.
import type { components } from '@/api/types'
import { Badge } from '@/components/ui/badge'
import { fieldLabel, formatTime, formatValue } from '@/format'
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

export function EventView(props: ViewProps) {
  const index = props.events.findIndex((event) => String(event.id) === String(props.target.id))
  if (index < 0) return <NotFound />
  const event = props.events[index]
  const previous = props.events[index - 1]
  const next = props.events[index + 1]
  return (
    <div className="flex flex-col gap-2 text-sm">
      <p className="flex flex-wrap items-center gap-2">
        <Badge variant="secondary">{EVENT_LABELS[event.type]}</Badge>
        <span>{`${ACTOR_LABELS[event.actor]}, ${formatTime(event.sim_ts)}`}</span>
      </p>
      <p>{event.summary}</p>
      <p className="flex gap-4">
        {previous !== undefined && <OpenLink onClick={() => openEvent(props, previous)}>Previous</OpenLink>}
        {next !== undefined && <OpenLink onClick={() => openEvent(props, next)}>Next</OpenLink>}
      </p>
    </div>
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
        <p>{formatValue(fact.value)}</p>
        <p className="flex flex-wrap items-center gap-2">
          <Badge variant="secondary">{SOURCE_LABELS[fact.source]}</Badge>
          {source !== undefined && <span>{`Observed ${formatTime(source.sim_ts)}`}</span>}
        </p>
        {source !== undefined && <OpenLink onClick={() => openEvent(props, source)}>{`Event #${source.id}`}</OpenLink>}
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
      <pre className="whitespace-pre-wrap rounded-md bg-muted p-3 font-sans">{draft.body}</pre>
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
      <pre className="whitespace-pre-wrap rounded-md bg-muted p-3 font-sans">{reply.message.body}</pre>
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
