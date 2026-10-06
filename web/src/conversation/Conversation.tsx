// ABOUTME: The frame of one conversation: its header, the timeline given as children, the chat tail of typed messages below it, and the composer at the bottom.
// ABOUTME: The composer is disabled in replay with a note, since a typed question needs a live model; a turn's progress scrolls the conversation to its end.
import { useEffect, useRef, type ReactNode } from 'react'
import type { components } from '@/api/types'
import { ChatTail } from '@/chat/ChatTail'
import { Composer } from '@/chat/Composer'
import { QUEUE, type Chat, type PanelTarget } from '@/surface'

type Schemas = components['schemas']

// What every conversation is given by the shell.
export type ConversationProps = {
  run: Schemas['RunView']
  proposals: Schemas['ProposalView'][]
  chat: Chat
  refresh: number
  onOpen: (target: PanelTarget) => void
  onSelect: (conversation: string) => void
  onChange: () => void
}

type Props = ConversationProps & {
  conversation: string
  title: string
  headerAction?: ReactNode
  placeholder: string
  children: ReactNode
}

const NEEDS_LIVE_MODE = 'Questions need live mode'

export function Conversation(props: Props) {
  const { conversation, title, headerAction, placeholder, children } = props
  // The lead the conversation's cards sit on; the queue holds the cards of no lead.
  const leadId = conversation === QUEUE ? null : conversation
  const { run, proposals, chat, onOpen, onSelect, onChange } = props
  const replay = run.mode === 'replay'
  const turns = chat.turnsOf(conversation)
  const latest = turns.at(-1)
  const end = useRef<HTMLDivElement>(null)
  // A message the underwriter sends, each lookup and the closing bring the end into view; opening a conversation does not.
  useEffect(() => {
    if (latest !== undefined) end.current?.scrollIntoView({ block: 'end' })
  }, [turns.length, latest?.steps.length, latest?.closing])
  return (
    <section aria-label="Conversation" className="flex h-full flex-col">
      <header className="flex items-center justify-between gap-4 border-b px-6 py-3">
        <h1 className="text-base font-semibold">{title}</h1>
        {headerAction}
      </header>
      <div className="min-h-0 flex-1 overflow-y-auto px-6 py-4">
        {/* The column is narrow enough to stay clear of the demo controls at the narrowest supported width. */}
        <div className="flex max-w-2xl flex-col gap-4">
          {children}
          <ChatTail
            turns={turns}
            proposals={proposals.filter((proposal) => proposal.lead_id === leadId)}
            leadId={leadId}
            onOpen={onOpen}
            onSelect={onSelect}
            onChange={onChange}
          />
          <div ref={end} />
        </div>
      </div>
      <Composer
        placeholder={placeholder}
        disabled={replay || chat.running}
        note={replay ? NEEDS_LIVE_MODE : null}
        onSend={(message) => chat.send(conversation, message)}
      />
    </section>
  )
}
