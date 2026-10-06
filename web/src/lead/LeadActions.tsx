// ABOUTME: The actions on a whole lead: resolve a fact, decline the lead, and paste a producer's reply to the lead's latest sent request.
// ABOUTME: Each form requires its reason, or the reply text, and shows the reason the command was refused.
import { declineLead, deliverReply, resolveFact } from '@/api/client'
import type { components } from '@/api/types'
import { ActionForm } from '@/components/ActionForm'

type LeadDetail = components['schemas']['LeadDetail']

type Props = { lead: LeadDetail; onChange: () => void }

const REASON = { name: 'reason', label: 'Reason' }

// The command takes a number or a flag as such: a fact that is held as one is sent as one, and
// a fact not held yet is sent as a number when the text is one.
function factValue(text: string, held: unknown): string | number | boolean {
  const value = text.trim()
  if (typeof held === 'boolean') return value.toLowerCase() === 'true'
  if (typeof held === 'number' || (held === undefined && /^-?\d+(\.\d+)?$/.test(value))) {
    return Number(value)
  }
  return value
}

export function LeadActions({ lead, onChange }: Props) {
  const terminal = lead.status === 'quote_sent' || lead.status === 'declined'
  const sentRequests = lead.drafts.filter(
    (draft) =>
      draft.state === 'sent' &&
      (draft.kind === 'routine_request' || draft.kind === 'sensitive_request'),
  )
  const latestRequest = sentRequests[sentRequests.length - 1]
  return (
    <div className="flex flex-col gap-4">
      {latestRequest !== undefined && (
        <ActionForm
          label="Paste a reply"
          fields={[{ name: 'body', label: 'The producer’s reply', multiline: true }]}
          act={({ body }) => deliverReply(lead.lead_id, latestRequest.intent_id, body!)}
          onDone={onChange}
        />
      )}
      {!terminal && (
        <>
          <ActionForm
            label="Resolve fact"
            fields={[
              { name: 'key', label: 'Field' },
              { name: 'value', label: 'Value' },
              REASON,
            ]}
            act={({ key, value, reason }) =>
              resolveFact(
                lead.lead_id,
                key!.trim(),
                factValue(value!, lead.facts.find((fact) => fact.key === key!.trim())?.value),
                reason!,
              )
            }
            onDone={onChange}
          />
          <ActionForm
            label="Decline lead"
            fields={[REASON]}
            act={({ reason }) => declineLead(lead.lead_id, reason!)}
            onDone={onChange}
          />
        </>
      )}
    </div>
  )
}
