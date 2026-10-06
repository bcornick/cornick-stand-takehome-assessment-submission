// ABOUTME: One lead's conversation: its persisted timeline, oldest first, in the conversation frame, with the "Full detail" link in the header.
// ABOUTME: Loads the lead's detail and events together and refetches them with the page; a request that fails shows a plain message.
import { getLead, getLeadEvents } from '@/api/client'
import { useRemote } from '@/api/useRemote'
import { leadName } from '@/format'
import type { components } from '@/api/types'
import { OpenItem } from '@/lead/ItemActions'
import { AssistantLabel } from './AssistantLabel'
import { Conversation, type ConversationProps } from './Conversation'
import { Narrative } from './Narrative'

type Props = ConversationProps & { leadId: string }

const NOT_SHOWN = ['model_called', 'skill_fallback_used', 'replay_miss', 'fault_injected']

// The events the narrative shows as steps: not the assistant's own, not model or replay bookkeeping, not a close that a card shows.
export function shownSteps(events: components['schemas']['EventRow'][]): number {
  return events.filter(
    (event) =>
      event.actor !== 'assistant' &&
      !NOT_SHOWN.includes(event.type) &&
      !(event.type === 'blocker_closed' && event.item_id !== null),
  ).length
}

export function LeadConversation({ leadId, ...shared }: Props) {
  const loaded = useRemote(
    leadId,
    () => Promise.all([getLead(leadId), getLeadEvents(leadId)]),
    shared.refresh,
  )
  if (loaded.state === 'loading') return <p role="status" className="p-6">{`Loading ${leadName(leadId)}`}</p>
  if (loaded.state === 'error') {
    return <p role="alert" className="p-6">{`Could not load ${leadName(leadId)}: ${loaded.message}.`}</p>
  }
  const [lead, { events }] = loaded.data
  const hasAddress = lead.label !== lead.lead_id
  return (
    <Conversation
      {...shared}
      conversation={leadId}
      title={hasAddress ? `${leadName(leadId)} · ${lead.label}` : leadName(leadId)}
      placeholder={`Ask about ${leadName(leadId).toLowerCase()}`}
      headerAction={
        <button
          type="button"
          className="text-sm underline underline-offset-2"
          onClick={() => shared.onOpen({ kind: 'lead', lead_id: leadId })}
        >
          Full detail
        </button>
      }
    >
      <div className="flex flex-col gap-1">
        <AssistantLabel />
        <p className="text-sm">{lead.summary}</p>
      </div>
      {lead.blockers.length > 0 && (
        <ul className="flex flex-col gap-3">
          {lead.blockers.map((blocker) => (
            <li key={blocker.item_id} className="rounded-md border bg-background p-3">
              <OpenItem lead={lead} blocker={blocker} onChange={shared.onChange} />
            </li>
          ))}
        </ul>
      )}
      <details>
        <summary className="cursor-pointer text-xs text-muted-foreground">
          {`Show the work (${shownSteps(events)} steps)`}
        </summary>
        <div className="mt-3">
          <Narrative lead={lead} events={events} onOpen={shared.onOpen} />
        </div>
      </details>
    </Conversation>
  )
}
