// ABOUTME: The typed messages of one conversation with what came back, and the open proposal cards that sit on its lead.
// ABOUTME: A turn shows its lookups as they happen, then its answer with its sources folded under "Related artifacts", one line each that opens the panel, its card or its error.
import type { components } from '@/api/types'
import { AssistantLabel } from '@/conversation/AssistantLabel'
import { leadName } from '@/format'
import { QUEUE, type PanelTarget, type Turn } from '@/surface'
import { AnswerText } from './AnswerText'
import { ProposalCard } from './ProposalCard'

type Props = {
  turns: Turn[]
  proposals: components['schemas']['ProposalView'][]
  leadId: string | null
  onOpen: (target: PanelTarget) => void
  onSelect: (conversation: string) => void
  onChange: () => void
}

type Citation = components['schemas']['Citation']

// An answer's citations in the order the lookups numbered them.
function sourcesOf(closing: Extract<Turn['closing'], { type: 'answer' }>) {
  return [...closing.citations].sort((a, b) => a.number - b.number)
}

// A source as one line: what it is, then its lead, which a lead's own line already names.
function sourceLine(citation: Citation): string {
  const text = citation.text.replace(/\.$/, '')
  return citation.kind === 'lead' ? text : `${text}, ${leadName(citation.lead_id).toLowerCase()}`
}

export function ChatTail({ turns, proposals, leadId, onOpen, onSelect, onChange }: Props) {
  return (
    <div className="flex flex-col gap-4">
      {turns.length > 0 && (
        <ol className="flex flex-col gap-4">
          {turns.map((turn, index) => {
            const { closing } = turn
            return (
              <li key={index} className="flex flex-col gap-2">
                <p className="max-w-[80%] self-end rounded-md bg-background px-3 py-1.5 text-sm">{turn.message}</p>
                {turn.steps.length > 0 && (
                  <details open={closing === null} className="text-xs text-muted-foreground">
                    <summary>What I looked at</summary>
                    <ul>
                      {turn.steps.map((step, stepIndex) => (
                        <li key={stepIndex}>{step}</li>
                      ))}
                    </ul>
                  </details>
                )}
                {closing === null && <p className="text-xs text-accent">Working…</p>}
                {closing?.type === 'answer' && (
                  <div className="flex flex-col gap-1">
                    <AssistantLabel />
                    <AnswerText answer={closing.answer} />
                    {closing.citations.length > 0 && (
                      <details className="text-xs text-muted-foreground">
                        <summary>{`Related artifacts (${closing.citations.length})`}</summary>
                        <ul aria-label="Related artifacts" className="flex flex-col gap-0.5">
                          {sourcesOf(closing).map((citation) => (
                            <li key={citation.number}>
                              <button
                                type="button"
                                className="text-left hover:underline"
                                onClick={() => onOpen({ kind: citation.kind, lead_id: citation.lead_id, id: citation.id })}
                              >
                                {sourceLine(citation)}
                              </button>
                            </li>
                          ))}
                        </ul>
                      </details>
                    )}
                  </div>
                )}
                {closing?.type === 'error' && (
                  <p role="alert" className="text-sm text-destructive">{`Could not get an answer: ${closing.reason}.`}</p>
                )}
                {closing?.type === 'proposal' && closing.lead_id !== leadId && (
                  <button
                    type="button"
                    onClick={() => onSelect(closing.lead_id ?? QUEUE)}
                    className="self-start text-xs underline"
                  >
                    {closing.lead_id === null ? 'Proposed on the queue' : `Proposed on ${leadName(closing.lead_id)}`}
                  </button>
                )}
              </li>
            )
          })}
        </ol>
      )}
      {proposals.length > 0 && (
        <ul aria-label="Proposals" className="flex flex-col gap-2">
          {proposals.map((proposal) => (
            <ProposalCard key={proposal.proposal_id} proposal={proposal} onDone={onChange} />
          ))}
        </ul>
      )}
    </div>
  )
}
