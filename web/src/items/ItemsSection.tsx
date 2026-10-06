// ABOUTME: The open items across leads: one row per review, question card or unknown delivery, with a button that opens its lead.
// ABOUTME: Rows keep the order the API returns.
import type { components } from '@/api/types'
import { Badge } from '@/components/ui/badge'
import { BLOCKER_KIND_LABELS } from '@/labels'

type Item = components['schemas']['Item']

type Props = { items: Item[]; onSelect: (leadId: string) => void }

export function ItemsSection({ items, onSelect }: Props) {
  return (
    <section aria-labelledby="open-items" className="flex flex-col gap-2">
      <h2 id="open-items" className="text-lg font-medium">
        Open items
      </h2>
      {items.length === 0 ? (
        <p className="text-sm text-muted-foreground">No items are open.</p>
      ) : (
        <ul className="flex flex-col gap-1">
          {items.map((item) => (
            <li key={item.item_id} className="flex flex-wrap items-baseline gap-2 text-sm">
              <Badge variant="outline">{BLOCKER_KIND_LABELS[item.kind]}</Badge>
              <button
                type="button"
                className="font-mono underline underline-offset-2 focus-visible:ring-3 focus-visible:ring-ring/50 outline-none"
                onClick={() => onSelect(item.lead_id)}
              >
                {`Open ${item.lead_id}`}
              </button>
              <span>{item.detail.text}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
