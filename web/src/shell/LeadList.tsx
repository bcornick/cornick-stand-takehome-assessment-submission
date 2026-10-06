// ABOUTME: The left column: the name STAND in capitals, the "Queue" entry and the leads in their groups.
// ABOUTME: Rows keep the order the API returns.
import type { components } from '@/api/types'
import { Badge } from '@/components/ui/badge'
import { formatDate, leadName } from '@/format'
import { GROUP_LABELS, GROUP_ORDER } from '@/labels'
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

// What differs between leads: who the lead waits on, or that it is finished.
function chipLabel(row: Schemas['QueueRow']): string | null {
  if (row.status === 'quote_sent') return 'Quote sent'
  if (row.status === 'declined') return 'Declined'
  if (row.waits_on === 'underwriter') return 'Needs your decision'
  if (row.waits_on === 'producer') return 'Waiting on producer'
  if (row.waits_on === 'data_team') return 'Waiting on data'
  return null
}

function queueTime(businessDays: number): string {
  const days = Math.round(businessDays)
  if (businessDays < 0.5) return 'in queue today'
  return `${days} ${days === 1 ? 'day' : 'days'} in queue`
}

function LeadRow({ row, isSelected, onSelect }: RowProps) {
  const chip = chipLabel(row)
  return (
    <button
      type="button"
      aria-current={isSelected ? 'true' : undefined}
      onClick={() => onSelect(row.lead_id)}
      className={entryClass(isSelected)}
    >
      <span className="flex items-center justify-between gap-2">
        <span className="font-medium">{leadName(row.lead_id)}</span>
        {chip !== null && <Badge variant="secondary">{chip}</Badge>}
      </span>
      <span className="block truncate">{row.label === row.lead_id ? 'no address' : row.label}</span>
      <span className="block text-xs text-muted-foreground">
        {row.effective_date === null ? 'No effective date' : `Effective ${formatDate(row.effective_date)}`}
        {` · ${queueTime(row.age_business_days)}`}
        {row.service_level_breached && ' · Past service level'}
      </span>
    </button>
  )
}

export function LeadList({ run, rows, selected, onSelect }: Props) {
  return (
    <nav aria-label="Leads" className="h-full overflow-y-auto border-r">
      <div className="px-4 py-3">
        <h1 className="text-4xl font-semibold tracking-wide">STAND</h1>
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
