// ABOUTME: The left column: the name STAND in capitals, the run summary sentence, the "Queue" entry and the leads in their groups.
// ABOUTME: Rows keep the order the API returns.
import type { components } from '@/api/types'
import { Badge } from '@/components/ui/badge'
import { MISSING, leadName, summarySentence } from '@/format'
import { BLOCKER_KIND_LABELS, GROUP_LABELS, GROUP_ORDER, STATUS_LABELS } from '@/labels'
import { QUEUE } from '@/surface'

type Schemas = components['schemas']

type Props = {
  run: Schemas['RunView']
  rows: Schemas['QueueRow'][]
  selected: string
  onSelect: (conversation: string) => void
}

const entryClass = (isSelected: boolean) =>
  `block w-full border-l-2 px-4 py-2 text-left text-sm ${
    isSelected ? 'border-accent bg-muted' : 'border-transparent hover:bg-muted'
  }`

type RowProps = {
  row: Schemas['QueueRow']
  isSelected: boolean
  onSelect: (conversation: string) => void
}

function LeadRow({ row, isSelected, onSelect }: RowProps) {
  return (
    <button
      type="button"
      aria-current={isSelected ? 'true' : undefined}
      onClick={() => onSelect(row.lead_id)}
      className={entryClass(isSelected)}
    >
      <span className="flex items-center justify-between gap-2">
        <span className="font-medium">{leadName(row.lead_id)}</span>
        <Badge variant="secondary">{STATUS_LABELS[row.status]}</Badge>
      </span>
      <span className="block truncate">{row.label === row.lead_id ? 'no address' : row.label}</span>
      <span className="block text-muted-foreground">
        {row.primary_next_action === null
          ? 'Nothing waiting'
          : BLOCKER_KIND_LABELS[row.primary_next_action]}
      </span>
      <span className="block text-xs text-muted-foreground">
        {row.effective_date ?? MISSING} · {row.age_business_days.toFixed(1)} days
        {row.service_level_breached && ' · Past service level'}
      </span>
    </button>
  )
}

export function LeadList({ run, rows, selected, onSelect }: Props) {
  return (
    <nav aria-label="Leads" className="h-full overflow-y-auto border-r">
      <div className="px-4 py-3">
        <h1 className="text-lg font-semibold tracking-wide">STAND</h1>
        <p className="text-xs text-muted-foreground">{summarySentence(run.summary)}</p>
      </div>
      <button
        type="button"
        aria-current={selected === QUEUE ? 'true' : undefined}
        onClick={() => onSelect(QUEUE)}
        className={entryClass(selected === QUEUE)}
      >
        Queue
      </button>
      {run.run_id === null ? (
        <p className="px-4 py-3 text-sm text-muted-foreground">
          No leads are loaded. Use Demo controls, bottom right.
        </p>
      ) : (
        GROUP_ORDER.map((group) => {
          const inGroup = rows.filter((row) => row.group === group)
          if (inGroup.length === 0) return null
          return (
            <section key={group} aria-label={GROUP_LABELS[group]}>
              <h2 className="px-4 pb-1 pt-4 text-xs font-medium uppercase text-muted-foreground">
                {GROUP_LABELS[group]}
              </h2>
              {inGroup.map((row) => (
                <LeadRow
                  key={row.lead_id}
                  row={row}
                  isSelected={selected === row.lead_id}
                  onSelect={onSelect}
                />
              ))}
            </section>
          )
        })
      )}
    </nav>
  )
}
