// ABOUTME: One lead's conversation: its persisted timeline, oldest first, in the conversation frame, with the "Full detail" link in the header.
// ABOUTME: Loads the lead's detail and events together and refetches them with the page; a request that fails shows a plain message.
import { getLead, getLeadEvents } from '@/api/client'
import { useRemote } from '@/api/useRemote'
import { leadName } from '@/format'
import { OpenItem } from '@/lead/ItemActions'
import { AssistantLabel } from './AssistantLabel'
import { Conversation, type ConversationProps } from './Conversation'
import { type Block, narrate } from './narrate'
import { Narrative } from './Narrative'

type Props = ConversationProps & { leadId: string }

// The lines the timeline shows: a bullet, a folded run, a bubble, a card or the underwriter's line each count once.
export function shownSteps(blocks: Block[]): number {
  return blocks.reduce((count, block) => count + (block.kind === 'assistant_message' ? block.bullets.length : 1), 0)
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
  const latest = events.at(-1)
  const hasAddress = lead.label !== lead.lead_id
  return (
    <Conversation
      {...shared}
      conversation={leadId}
      title={hasAddress ? `${leadName(leadId)} · ${lead.label}` : leadName(leadId)}
      placeholder={`Ask about ${leadName(leadId).toLowerCase()}`}
      headerAction={
        // The link goes while the panel shows this lead's full detail, and returns when it closes.
        shared.panel?.kind === 'lead' && shared.panel.lead_id === leadId ? null : (
          <button
            type="button"
            className="text-sm underline underline-offset-2"
            onClick={() => shared.onOpen({ kind: 'lead', lead_id: leadId })}
          >
            Full detail
          </button>
        )
      }
    >
      <div className="flex flex-col gap-1">
        <AssistantLabel />
        <p className="text-sm">{lead.summary}</p>
      </div>
      {latest !== undefined && (
        // The timeline is one click away: the panel's event view, with the latest event expanded.
        <button
          type="button"
          className="button-outline self-start"
          onClick={() => shared.onOpen({ kind: 'event', lead_id: leadId, id: latest.id })}
        >
          View event timeline
        </button>
      )}
      {lead.blockers.length > 0 && (
        <ul className="flex flex-col gap-3">
          {lead.blockers.filter((blocker) => blocker.owner === 'underwriter').map((blocker) => (
            <li key={blocker.item_id} className="rounded-md border border-l-[3px] border-l-accent bg-background p-3">
              <OpenItem lead={lead} blocker={blocker} onChange={shared.onChange} />
            </li>
          ))}
        </ul>
      )}
      <details>
        <summary className="cursor-pointer text-xs text-muted-foreground">
          {`Show the work (${shownSteps(narrate(events, lead))} steps)`}
        </summary>
        <div className="mt-3">
          <Narrative lead={lead} events={events} onOpen={shared.onOpen} />
        </div>
      </details>
    </Conversation>
  )
}
