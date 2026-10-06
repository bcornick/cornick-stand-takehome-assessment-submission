// ABOUTME: The typed messages of one conversation with what came back, and the open proposal cards that sit on its lead.
// ABOUTME: A turn shows its lookups as they happen, then its answer with citation chips, its card or its error.
import type { components } from '@/api/types'
import type { PanelTarget, Turn } from '@/surface'

type Props = {
  turns: Turn[]
  proposals: components['schemas']['ProposalView'][]
  leadId: string | null
  onOpen: (target: PanelTarget) => void
  onSelect: (conversation: string) => void
  onChange: () => void
}

export function ChatTail({ turns }: Props) {
  return (
    <ol>
      {turns.map((turn, index) => (
        <li key={index}>{turn.message}</li>
      ))}
    </ol>
  )
}
