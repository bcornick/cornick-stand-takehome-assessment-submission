// ABOUTME: The queue-level conversation: the run summary as its first message, the open items of every lead as cards, and the example prompts while nothing has been asked.
// ABOUTME: A card shows its lead as a button that selects the lead's conversation, then the item with its actions.
import { getLead } from '@/api/client'
import type { components } from '@/api/types'
import { useRemote } from '@/api/useRemote'
import { leadName, summarySentence } from '@/format'
import { OpenItem } from '@/lead/ItemActions'
import { QUEUE } from '@/surface'
import { Conversation, type ConversationProps } from './Conversation'

type Item = components['schemas']['Item']

type Props = ConversationProps & { items: Item[] }

export function QueueConversation({ items, ...shared }: Props) {
  const { run, chat, refresh, onSelect, onChange } = shared
  const loaded = run.run_id !== null
  return (
    <Conversation {...shared} conversation={QUEUE} title="Queue" placeholder="Ask about the queue">
      {loaded ? (
        <>
          <p>{summarySentence(run.summary)}</p>
          {items.length === 0 ? (
            <p className="text-sm text-muted-foreground">Nothing is waiting on you.</p>
          ) : (
            <ul className="flex flex-col gap-3">
              {items.map((item) => (
                <li key={item.item_id}>
                  <ItemCard item={item} refresh={refresh} onSelect={onSelect} onChange={onChange} />
                </li>
              ))}
            </ul>
          )}
          {chat.turnsOf(QUEUE).length === 0 && run.example_prompts.length > 0 && (
            <div className="flex flex-col items-start gap-2">
              <p className="text-sm text-muted-foreground">Try asking:</p>
              {run.example_prompts.map((prompt) => (
                <button
                  key={prompt}
                  type="button"
                  className="button-outline"
                  disabled={chat.running}
                  onClick={() => chat.send(QUEUE, prompt)}
                >
                  {prompt}
                </button>
              ))}
            </div>
          )}
        </>
      ) : (
        <p className="text-sm text-muted-foreground">
          No leads are loaded. Use Demo controls, bottom right, to load today's leads.
        </p>
      )}
    </Conversation>
  )
}

type CardProps = Pick<ConversationProps, 'refresh' | 'onSelect' | 'onChange'> & { item: Item }

function ItemCard({ item, refresh, onSelect, onChange }: CardProps) {
  const lead = useRemote(item.lead_id, () => getLead(item.lead_id), refresh)
  if (lead.state === 'error') return <p className="text-sm">{`The lead could not be loaded: ${lead.message}`}</p>
  const blocker = lead.state === 'ready' ? lead.data.blockers.find((b) => b.item_id === item.item_id) : undefined
  if (lead.state === 'ready' && blocker === undefined) return null
  return (
    <div className="flex flex-col gap-2 rounded-md border p-3">
      <button
        type="button"
        className="self-start text-sm font-medium underline-offset-2 hover:underline"
        onClick={() => onSelect(item.lead_id)}
      >
        {lead.state === 'ready' && lead.data.label !== item.lead_id
          ? `${leadName(item.lead_id)} · ${lead.data.label}`
          : leadName(item.lead_id)}
      </button>
      {lead.state === 'ready' && blocker !== undefined ? (
        <OpenItem lead={lead.data} blocker={blocker} onChange={onChange} />
      ) : (
        <p>{item.detail.text}</p>
      )}
    </div>
  )
}
