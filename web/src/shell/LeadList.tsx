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
type State = 'needs' | 'waiting' | 'done'

// What differs between leads, as the chip says it and the state that colours it.
function chip(row: Schemas['QueueRow']): { label: string; state: State } | null {
  if (row.status === 'quote_sent') return { label: 'Quote sent', state: 'done' }
  if (row.status === 'declined') return { label: 'Declined', state: 'done' }
  if (row.waits_on === 'underwriter') return { label: 'Needs your decision', state: 'needs' }
  if (row.waits_on === 'producer') return { label: 'Waiting on producer', state: 'waiting' }
  if (row.waits_on === 'data_team') return { label: 'Waiting on data', state: 'waiting' }
  return null
}

function queueTime(businessDays: number): string {
  const days = Math.round(businessDays)
  if (businessDays < 0.5) return 'in queue today'
  return `${days} ${days === 1 ? 'day' : 'days'} in queue`
}

function LeadRow({ row, isSelected, onSelect }: RowProps) {
  const state = chip(row)
  return (
    <button
      type="button"
      aria-current={isSelected ? 'true' : undefined}
      onClick={() => onSelect(row.lead_id)}
      className={entryClass(isSelected)}
    >
      <span className="flex items-center justify-between gap-2">
        <span className="font-medium">{leadName(row.lead_id)}</span>
        {state !== null && <Badge variant={state.state}>{state.label}</Badge>}
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
      {/* The queue is the hub every lead returns to: it reads as a heading, with a mark, and a rule sets it off from the groups. */}
      <button
        type="button"
        aria-current={selected === QUEUE ? 'true' : undefined}
        onClick={() => onSelect(QUEUE)}
        className={`${entryClass(selected === QUEUE)} mb-1 flex items-center gap-2 border-b py-3 text-base font-semibold`}
      >
        <svg aria-hidden="true" viewBox="0 0 20 20" className="h-4 w-4 shrink-0" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
          <path d="M3 9.5 10 3.5l7 6" />
          <path d="M5 8.5V16h10V8.5" />
        </svg>
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
              <h2
                className={`flex items-center justify-between gap-2 px-4 pb-1 pt-4 text-xs font-medium uppercase whitespace-nowrap ${group === 'blocked_on_underwriter' ? 'text-accent' : 'text-muted-foreground'}`}
              >
                {GROUP_LABELS[group]}
                {group === 'blocked_on_underwriter' && <Badge variant="needs">{`Needs you · ${inGroup.length}`}</Badge>}
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
