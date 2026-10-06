// ABOUTME: The chat tails of the run, held in the browser's memory by conversation and lost on reload by design; a new run clears them.
// ABOUTME: Sending a message streams its turn into the tail of the conversation it was typed in.
import { useEffect, useRef, useState } from 'react'
import { getProposals, streamChat } from '@/api/client'
import type { components } from '@/api/types'
import { QUEUE, type Chat, type Closing, type Turn } from '@/surface'

type ProposalEvent = components['schemas']['ProposalEvent']

const HISTORY_TURNS = 4
// The length the server accepts for a message and a reply.
const TEXT_CAP = 2000

type Tails = Record<string, Turn[]>

// What a closed turn said back: the answer, the card's rationale or the error's reason.
function replyOf(closing: Closing): string {
  switch (closing.type) {
    case 'answer':
      return closing.answer
    case 'proposal':
      return closing.rationale
    case 'error':
      return closing.reason
  }
}

function historyOf(turns: Turn[]) {
  return turns
    .filter((turn): turn is Turn & { closing: Closing } => turn.closing !== null)
    .slice(-HISTORY_TURNS)
    .map((turn) => ({
      message: turn.message.slice(0, TEXT_CAP),
      reply: replyOf(turn.closing).slice(0, TEXT_CAP),
    }))
}

async function rationaleOf(proposalId: number): Promise<string> {
  const cards = await getProposals()
  const payload = cards.find((card) => card.proposal_id === proposalId)?.payload as { rationale?: string } | undefined
  return payload?.rationale ?? ''
}

export function useChat(runId: string | null, onProposal: () => void): Chat {
  const [tails, setTails] = useState<Tails>({})
  const [inFlight, setInFlight] = useState(0)
  const tailsRef = useRef(tails)
  tailsRef.current = tails

  useEffect(() => setTails({}), [runId])

  async function send(conversation: string, message: string) {
    const history = historyOf(tailsRef.current[conversation] ?? [])
    let current: Turn = { message, steps: [], closing: null }
    // Replaces the turn in its tail with the changed turn; the turn is found by identity, so a re-render cannot misplace it.
    const change = (update: (turn: Turn) => Turn) => {
      const before = current
      const after = update(before)
      current = after
      setTails((past) => ({ ...past, [conversation]: (past[conversation] ?? []).map((turn) => (turn === before ? after : turn)) }))
    }
    setTails((past) => ({ ...past, [conversation]: [...(past[conversation] ?? []), current] }))
    setInFlight((count) => count + 1)
    try {
      let proposed: ProposalEvent | null = null
      await streamChat({ message, lead_id: conversation === QUEUE ? null : conversation, history }, (event) => {
        if (event.type === 'step') change((turn) => ({ ...turn, steps: [...turn.steps, event.summary] }))
        else if (event.type === 'proposal') proposed = event
        else change((turn) => ({ ...turn, closing: event }))
      })
      // The card's rationale is read once the stream has closed, so the card exists on the server.
      const card = proposed as ProposalEvent | null
      if (card !== null) {
        const rationale = await rationaleOf(card.proposal_id)
        change((turn) => ({ ...turn, closing: { ...card, rationale } }))
        onProposal()
      }
    } catch (error) {
      const reason = error instanceof Error ? error.message : String(error)
      change((turn) => ({ ...turn, closing: { type: 'error', reason } }))
    } finally {
      setInFlight((count) => count - 1)
    }
  }

  return { turnsOf: (conversation) => tails[conversation] ?? [], running: inFlight > 0, send }
}
