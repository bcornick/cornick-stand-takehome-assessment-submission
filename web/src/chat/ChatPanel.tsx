// ABOUTME: The chat panel: a message box, each turn's steps as they happen, then its answer with numbered citations, and the open proposal cards with Apply and Dismiss.
// ABOUTME: A message goes to the open lead when one is selected. The cards come from the server, so a card outlives a reload; applying one tells the page to refetch.
import { useState, type FormEvent } from 'react'
import { getProposals, streamChat, type ChatEvent } from '@/api/client'
import { useRemote } from '@/api/useRemote'
import { ProposalCard } from './ProposalCard'

type Closing = Exclude<ChatEvent, { type: 'step' }>
type Exchange = { message: string; steps: string[]; closing: Closing | null }

type Props = { leadId: string | null; onChange: () => void }

export function ChatPanel({ leadId, onChange }: Props) {
  const [message, setMessage] = useState('')
  const [sending, setSending] = useState(false)
  const [exchanges, setExchanges] = useState<Exchange[]>([])
  const [cardsVersion, setCardsVersion] = useState(0)
  const cards = useRemote('proposals', getProposals, cardsVersion)

  // Changes the exchange of the turn in flight, which is always the last one.
  const updateTurn = (change: (turn: Exchange) => Exchange) =>
    setExchanges((past) => [...past.slice(0, -1), change(past[past.length - 1])])

  async function send(event: FormEvent) {
    event.preventDefault()
    const text = message.trim()
    if (text === '') return
    setSending(true)
    setMessage('')
    setExchanges((past) => [...past, { message: text, steps: [], closing: null }])
    try {
      await streamChat({ message: text, lead_id: leadId, history: [] }, (chatEvent) =>
        updateTurn((turn) =>
          chatEvent.type === 'step'
            ? { ...turn, steps: [...turn.steps, chatEvent.summary] }
            : { ...turn, closing: chatEvent },
        ),
      )
    } catch (error) {
      const reason = error instanceof Error ? error.message : String(error)
      updateTurn((turn) => ({ ...turn, closing: { type: 'error', reason } }))
    } finally {
      setSending(false)
      setCardsVersion((version) => version + 1)
    }
  }

  const cardsDone = () => {
    setCardsVersion((version) => version + 1)
    onChange()
  }

  return (
    <section aria-label="Assistant" className="flex flex-col gap-4">
      <h2 className="text-lg font-semibold">Assistant</h2>
      <ol className="flex flex-col gap-3">
        {exchanges.map((exchange, index) => (
          <li key={index} className="flex flex-col gap-1">
            <p className="text-sm font-medium">{exchange.message}</p>
            {exchange.steps.length > 0 && (
              <ul aria-label="Steps" className="text-xs text-muted-foreground">
                {exchange.steps.map((step, stepIndex) => (
                  <li key={stepIndex}>{step}</li>
                ))}
              </ul>
            )}
            {exchange.closing === null && <p className="text-xs text-muted-foreground">Working…</p>}
            {exchange.closing?.type === 'error' && (
              <p role="alert" className="text-sm text-destructive">{`Could not get an answer: ${exchange.closing.reason}.`}</p>
            )}
            {exchange.closing?.type === 'proposal' && <p className="text-sm">Proposed. Review the card below.</p>}
            {exchange.closing?.type === 'answer' && (
              <>
                <p className="text-sm">{exchange.closing.answer}</p>
                <p className="flex gap-1 font-mono text-xs text-muted-foreground">
                  {exchange.closing.citations.map((citation) => (
                    <span key={citation.number}>{`[${citation.number}]`}</span>
                  ))}
                </p>
              </>
            )}
          </li>
        ))}
      </ol>
      {cards.state === 'error' && <p role="alert">{`Could not load the proposals: ${cards.message}.`}</p>}
      {cards.state === 'ready' && cards.data.length > 0 && (
        <ul aria-label="Proposals" className="flex flex-col gap-2">
          {cards.data.map((proposal) => (
            <ProposalCard key={proposal.proposal_id} proposal={proposal} onDone={cardsDone} />
          ))}
        </ul>
      )}
      <form onSubmit={send} className="flex gap-2">
        <input
          aria-label="Message"
          value={message}
          onChange={(event) => setMessage(event.target.value)}
          className="min-w-0 flex-1 rounded-md border px-3 py-1.5 text-sm"
          placeholder={leadId === null ? 'Ask about the queue' : `Ask about ${leadId}`}
        />
        <button
          type="submit"
          disabled={sending}
          className="rounded-md border bg-primary px-3 py-1.5 text-sm text-primary-foreground disabled:opacity-50"
        >
          Send
        </button>
      </form>
    </section>
  )
}
