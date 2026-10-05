// ABOUTME: Root component of the underwriter surface: the queue page beside the detail pane of the selected lead.
// ABOUTME: Loads the run and the queue once; the selected lead is held in state, with no router.
import { useState } from 'react'
import { getLeads, getRun } from '@/api/client'
import { useRemote } from '@/api/useRemote'
import { LeadDetailPage } from '@/lead/LeadDetailPage'
import { QueuePage } from '@/queue/QueuePage'

function App() {
  const [selectedLeadId, setSelectedLeadId] = useState<string | null>(null)
  const queue = useRemote('queue', () => Promise.all([getRun(), getLeads()]))

  if (queue.state === 'loading') return <p role="status" className="p-6">Loading the queue</p>
  if (queue.state === 'error') {
    return <p role="alert" className="p-6">{`Could not load the queue: ${queue.message}.`}</p>
  }
  const [run, rows] = queue.data
  return (
    <main className="grid gap-8 p-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
      <QueuePage run={run} rows={rows} selectedLeadId={selectedLeadId} onSelect={setSelectedLeadId} />
      <aside aria-label="Lead detail">
        {selectedLeadId === null ? (
          <p className="text-sm text-muted-foreground">Select a lead to see its detail.</p>
        ) : (
          <LeadDetailPage leadId={selectedLeadId} />
        )}
      </aside>
    </main>
  )
}

export default App
