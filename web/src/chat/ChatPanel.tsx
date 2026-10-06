// ABOUTME: The chat panel: a message box, each answer with the event ids it cites, and the open proposal cards with Apply and Dismiss.
// ABOUTME: A message goes to the open lead when one is selected. The cards come from the server, so a card outlives a reload; applying one tells the page to refetch.
import { useState, type FormEvent } from 'react'
import { getProposals, sendChat } from '@/api/client'
import type { components } from '@/api/types'
import { useRemote } from '@/api/useRemote'
import { ProposalCard } from './ProposalCard'

type Answer = components['schemas']['ChatResponse']
type Exchange = { message: string; outcome: Answer | { error: string } }

type Props = { leadId: string | null; onChange: () => void }

export function ChatPanel({ leadId, onChange }: Props) {
  const [message, setMessage] = useState('')
  const [sending, setSending] = useState(false)
  const [exchanges, setExchanges] = useState<Exchange[]>([])
  const [cardsVersion, setCardsVersion] = useState(0)
  const cards = useRemote('proposals', getProposals, cardsVersion)

  async function send(event: FormEvent) {
    event.preventDefault()
    const text = message.trim()
    if (text === '') return
    setSending(true)
    try {
      const answer = await sendChat(text, leadId)
      setExchanges((past) => [...past, { message: text, outcome: answer }])
      setMessage('')
    } catch (error) {
      const reason = error instanceof Error ? error.message : String(error)
      setExchanges((past) => [...past, { message: text, outcome: { error: reason } }])
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
            {'error' in exchange.outcome ? (
              <p role="alert" className="text-sm text-destructive">{`Could not get an answer: ${exchange.outcome.error}.`}</p>
            ) : (
              <>
                <p className="text-sm">{exchange.outcome.answer}</p>
                {exchange.outcome.cited_event_ids.length > 0 && (
                  <p className="font-mono text-xs text-muted-foreground">
                    {`Events ${exchange.outcome.cited_event_ids.join(', ')}`}
                  </p>
                )}
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
