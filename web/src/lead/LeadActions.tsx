// ABOUTME: The actions on a whole lead: resolve a fact of the lead's registry fields, decline the lead, and paste a producer's reply to the lead's latest sent request.
// ABOUTME: Each form requires its reason, or the reply text, and shows the reason the command was refused.
import { declineLead, deliverReply, resolveFact } from '@/api/client'
import type { components } from '@/api/types'
import { ActionForm } from '@/components/ActionForm'

type LeadDetail = components['schemas']['LeadDetail']

type Props = { lead: LeadDetail; onChange: () => void }

const REASON = { name: 'reason', label: 'Reason' }

// The command carries the value as the field's registry type: a number for an integer or a decimal, a
// flag for a toggle, and text for every other type, so a zip code stays "34102". Text that does not fit
// the type is sent as it is, and the command refuses it with the reason.
function factValue(text: string, kind: string): string | number | boolean {
  const value = text.trim()
  const flag = value.toLowerCase()
  if (kind === 'toggle' && (flag === 'true' || flag === 'yes')) return true
  if (kind === 'toggle' && (flag === 'false' || flag === 'no')) return false
  if ((kind === 'integer' || kind === 'decimal') && value !== '' && !Number.isNaN(Number(value))) {
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
              {
                name: 'key',
                label: 'Field',
                options: lead.fields.map((field) => ({
                  value: field.key,
                  label: `${field.label} (${field.key})`,
                })),
              },
              { name: 'value', label: 'Value' },
              REASON,
            ]}
            act={({ key, value, reason }) =>
              resolveFact(
                lead.lead_id,
                key!,
                factValue(value!, lead.fields.find((field) => field.key === key)!.kind),
                reason!,
              )
            }
            onDone={onChange}
          />
          <ActionForm
            label="Decline lead"
            destructive
            fields={[REASON]}
            act={({ reason }) => declineLead(lead.lead_id, reason!)}
            onDone={onChange}
          />
        </>
      )}
    </div>
  )
}
