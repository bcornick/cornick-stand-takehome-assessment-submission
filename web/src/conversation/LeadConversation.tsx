// ABOUTME: One lead's conversation: its persisted timeline, oldest first, in the conversation frame, with the "Full detail" link in the header.
// ABOUTME: Loads the lead's detail and events together and refetches them with the page; a request that fails shows a plain message.
import { getLead, getLeadEvents } from '@/api/client'
import { useRemote } from '@/api/useRemote'
import { leadName } from '@/format'
import { Conversation, type ConversationProps } from './Conversation'
import { Narrative } from './Narrative'

type Props = ConversationProps & { leadId: string }

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
      leadId={leadId}
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
      <Narrative lead={lead} events={events} onOpen={shared.onOpen} onChange={shared.onChange} />
    </Conversation>
  )
}
