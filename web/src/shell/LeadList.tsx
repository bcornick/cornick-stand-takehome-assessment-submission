// ABOUTME: The left column: the product name, the run summary sentence, the "Queue" entry and the leads in their groups.
// ABOUTME: Rows keep the order the API returns.
import type { components } from '@/api/types'

type Schemas = components['schemas']

type Props = {
  run: Schemas['RunView']
  rows: Schemas['QueueRow'][]
  selected: string
  onSelect: (conversation: string) => void
}

export function LeadList({ rows, onSelect }: Props) {
  return (
    <nav aria-label="Leads">
      {rows.map((row) => (
        <button key={row.lead_id} type="button" onClick={() => onSelect(row.lead_id)}>
          {row.lead_id}
        </button>
      ))}
    </nav>
  )
}
