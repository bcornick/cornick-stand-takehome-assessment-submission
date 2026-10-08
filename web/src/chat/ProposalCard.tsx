// ABOUTME: One proposal card of a conversation's chat tail: the command the assistant proposes in words with its reason, an Apply button that submits the command as the underwriter, and a Dismiss button.
// ABOUTME: A refused command shows its reason beside the button and the card stays; nothing runs until Apply is pressed.
import { applyProposal, dismissProposal } from '@/api/client'
import type { components } from '@/api/types'
import { ActionButton } from '@/components/ActionButton'
import { formatValue, shortLeadId } from '@/format'

type Proposal = components['schemas']['ProposalView']

type Props = { proposal: Proposal; onDone: () => void }

// The proposed command as a sentence the underwriter reads, from its type and payload.
function inWords(type: string, payload: Record<string, unknown>): string {
  switch (type) {
    case 'decline_lead':
      return `Decline lead ${shortLeadId(String(payload.lead_id))}`
    case 'resolve_fact':
      return `Set ${payload.key} to ${formatValue(payload.value)} on lead ${shortLeadId(String(payload.lead_id))}`
    case 'record_ruling':
      return `Choose ${String(payload.option).replace(/_/g, ' ')} for ${payload.choice_id} on lead ${shortLeadId(String(payload.lead_id))}`
    case 'edit_draft':
      return `Edit the draft ${payload.intent_id}`
    default:
      return type.replace(/_/g, ' ')
  }
}

export function ProposalCard({ proposal, onDone }: Props) {
  const { type, payload, rationale } = proposal.payload as {
    type: string
    payload: Record<string, unknown>
    rationale: string
  }
  return (
    <li className="flex flex-col gap-2 rounded-md border bg-background p-3">
      <p className="text-sm">
        <span className="font-medium">{inWords(type, payload)}</span>
        {': '}
        <span>{rationale}</span>
      </p>
      <span className="flex flex-wrap gap-2">
        <ActionButton
          label="Apply"
          act={async () => {
            const result = await applyProposal(proposal.proposal_id)
            return result.accepted ? null : (result.reason ?? 'The command was refused.')
          }}
          onDone={onDone}
        />
        <ActionButton
          label="Dismiss"
          act={async () => {
            await dismissProposal(proposal.proposal_id)
            return null
          }}
          onDone={onDone}
        />
      </span>
    </li>
  )
}
