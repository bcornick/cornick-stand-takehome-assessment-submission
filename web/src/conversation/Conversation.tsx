// ABOUTME: The frame of one conversation: its header, the timeline given as children, the chat tail of typed messages below it, and the composer at the bottom.
// ABOUTME: The composer is disabled in replay with a note, since a typed question needs a live model.
import type { ReactNode } from 'react'
import type { components } from '@/api/types'
import { ChatTail } from '@/chat/ChatTail'
import { Composer } from '@/chat/Composer'
import type { Chat, PanelTarget } from '@/surface'

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
  // The lead the conversation's cards sit on; null for the queue, which holds the cards of no lead.
  leadId: string | null
  headerAction?: ReactNode
  placeholder: string
  children: ReactNode
}

export const NEEDS_LIVE_MODE = 'Questions need live mode'

export function Conversation(props: Props) {
  const { conversation, title, leadId, headerAction, placeholder, children } = props
  const { run, proposals, chat, onOpen, onSelect, onChange } = props
  const replay = run.mode === 'replay'
  return (
    <section aria-label="Conversation" className="flex h-full flex-col">
      <header className="flex items-center justify-between gap-4 border-b px-6 py-3">
        <h1 className="text-base font-semibold">{title}</h1>
        {headerAction}
      </header>
      <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-6 py-4">
        {children}
        <ChatTail
          turns={chat.turnsOf(conversation)}
          proposals={proposals.filter((proposal) => proposal.lead_id === leadId)}
          leadId={leadId}
          onOpen={onOpen}
          onSelect={onSelect}
          onChange={onChange}
        />
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
