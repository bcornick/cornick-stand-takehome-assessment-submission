// ABOUTME: The queue-level conversation: the run summary as its first message, the open items of every lead as cards, and the example prompts while nothing has been asked.
// ABOUTME: A card with no lead sits in this conversation's tail.
import type { components } from '@/api/types'
import { summarySentence } from '@/format'
import { QUEUE } from '@/surface'
import { Conversation, type ConversationProps } from './Conversation'

type Props = ConversationProps & { items: components['schemas']['Item'][] }

export function QueueConversation({ items, ...shared }: Props) {
  return (
    <Conversation {...shared} conversation={QUEUE} leadId={null} title="Queue" placeholder="Ask about the queue">
      <p>{summarySentence(shared.run.summary)}</p>
      <p>{`${items.length} open items`}</p>
    </Conversation>
  )
}
