// ABOUTME: The queue-level conversation: the queue greeting as its first message and the open items of every lead as cards.
// ABOUTME: A card shows its lead as a button that selects the lead's conversation, then the item with its actions.
import { getLead } from '@/api/client'
import type { components } from '@/api/types'
import { useRemote } from '@/api/useRemote'
import { greeting, leadName } from '@/format'
import { OpenItem } from '@/lead/ItemActions'
import { QUEUE } from '@/surface'
import { AssistantLabel } from './AssistantLabel'
import { Conversation, type ConversationProps } from './Conversation'

type Item = components['schemas']['Item']

type Props = ConversationProps & { items: Item[] }

export function QueueConversation({ items, ...shared }: Props) {
  const { run, refresh, onSelect, onChange } = shared
  const loaded = run.run_id !== null
  return (
    <Conversation
      {...shared}
      conversation={QUEUE}
      title="Queue"
      placeholder="Ask about the queue"
      suggestions={loaded ? run.example_prompts : undefined}
    >
      {loaded ? (
        <>
          <div className="flex flex-col gap-1">
            <AssistantLabel />
            <p className="text-sm">
              {/* The greeting opens with the count of leads that need the underwriter; it alone is in the accent. */}
              <span className="font-semibold text-accent">{greeting(run.summary).split(' ')[0]}</span>
              {greeting(run.summary).slice(greeting(run.summary).indexOf(' '))}
            </p>
          </div>
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
    <div className="flex flex-col gap-2 rounded-md border border-l-[3px] border-l-accent bg-background p-3">
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
