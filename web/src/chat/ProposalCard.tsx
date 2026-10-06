// ABOUTME: One proposal card of the chat panel: the command the assistant proposes with its payload and its reason, an Apply button that submits the command as the underwriter, and a Dismiss button.
// ABOUTME: A refused command shows its reason beside the button and the card stays; nothing runs until Apply is pressed.
import { applyProposal, dismissProposal } from '@/api/client'
import type { components } from '@/api/types'
import { ActionButton } from '@/components/ActionButton'

type Proposal = components['schemas']['ProposalView']

type Props = { proposal: Proposal; onDone: () => void }

export function ProposalCard({ proposal, onDone }: Props) {
  const { type, payload, rationale } = proposal.payload as {
    type: string
    payload: Record<string, unknown>
    rationale: string
  }
  return (
    <li className="flex flex-col gap-2 rounded-md border p-3">
      <p className="text-sm">{rationale}</p>
      <p className="font-mono text-xs text-muted-foreground">{`${type} ${JSON.stringify(payload)}`}</p>
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
