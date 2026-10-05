// ABOUTME: The queue page: the mode label, the start control, the one-sentence run summary and one table per queue group.
// ABOUTME: Rows keep the order the API returns; the page groups them under headings and never re-sorts.
import type { components } from '@/api/types'
import { Badge } from '@/components/ui/badge'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { startRun } from '@/api/client'
import { ActionButton } from '@/components/ActionButton'
import { MISSING } from '@/format'
import {
  BLOCKER_KIND_LABELS,
  GROUP_LABELS,
  GROUP_ORDER,
  OWNER_LABELS,
  STATUS_LABELS,
} from '@/labels'

type RunView = components['schemas']['RunView']
type QueueRow = components['schemas']['QueueRow']

type Props = {
  run: RunView
  rows: QueueRow[]
  selectedLeadId: string | null
  onSelect: (leadId: string) => void
  onChange: () => void
}

function summarySentence(summary: RunView['summary']): string {
  return (
    `${summary.quotes_sent} quotes sent, ${summary.follow_ups_sent} follow-ups sent, ` +
    `${summary.declines_approved} declines approved, ` +
    `${summary.waiting_on_underwriter} waiting on the underwriter, ` +
    `${summary.waiting_on_producer} waiting on the producer, ` +
    `${summary.waiting_on_data} waiting on data, ${summary.delivery_unknown} delivery unknown.`
  )
}

export function QueuePage({ run, rows, selectedLeadId, onSelect, onChange }: Props) {
  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold">Underwriting triage</h1>
        <p className="flex flex-wrap items-center gap-2 text-sm">
          <Badge variant="outline">{`Mode: ${run.mode}`}</Badge>
          <span>{run.run_id === null ? 'No run started' : `Run ${run.run_id}`}</span>
        </p>
        <ActionButton
          label="Start morning run"
          act={async () => {
            await startRun()
            return null
          }}
          onDone={onChange}
        />
        <p className="text-base">{summarySentence(run.summary)}</p>
      </header>
      {GROUP_ORDER.map((group) => {
        const groupRows = rows.filter((row) => row.group === group)
        if (groupRows.length === 0) return null
        return (
          <section key={group} className="flex flex-col gap-2">
            <h2 className="text-lg font-medium">{GROUP_LABELS[group]}</h2>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Lead</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Next action</TableHead>
                  <TableHead>Waits on</TableHead>
                  <TableHead>Age (assumed two-business-day service level)</TableHead>
                  <TableHead>Effective date</TableHead>
                  <TableHead>Asks</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {groupRows.map((row) => (
                  <QueueRowView
                    key={row.lead_id}
                    row={row}
                    selected={row.lead_id === selectedLeadId}
                    onSelect={onSelect}
                  />
                ))}
              </TableBody>
            </Table>
          </section>
        )
      })}
    </div>
  )
}

type RowProps = { row: QueueRow; selected: boolean; onSelect: (leadId: string) => void }

function QueueRowView({ row, selected, onSelect }: RowProps) {
  return (
    <TableRow className={selected ? 'bg-muted' : undefined}>
      <TableCell>
        <button
          type="button"
          className="font-mono underline underline-offset-2 focus-visible:ring-3 focus-visible:ring-ring/50 outline-none"
          aria-current={selected ? 'true' : undefined}
          onClick={() => onSelect(row.lead_id)}
        >
          {row.lead_id}
        </button>
        <p className="text-sm text-muted-foreground">{row.label}</p>
      </TableCell>
      <TableCell>
        <Badge variant="secondary">{STATUS_LABELS[row.status]}</Badge>
      </TableCell>
      <TableCell>
        {row.primary_next_action === null ? MISSING : BLOCKER_KIND_LABELS[row.primary_next_action]}
      </TableCell>
      <TableCell>{row.waits_on === null ? MISSING : OWNER_LABELS[row.waits_on]}</TableCell>
      <TableCell>
        <span>{`${row.age_business_days.toFixed(2)} days`}</span>
        {row.service_level_breached && (
          <Badge variant="destructive" className="ml-2">
            Past service level
          </Badge>
        )}
      </TableCell>
      <TableCell>{row.effective_date ?? MISSING}</TableCell>
      <TableCell>{row.ask_count}</TableCell>
    </TableRow>
  )
}
