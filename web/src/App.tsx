// ABOUTME: Root component of the underwriter surface: the queue page and the open items beside the detail pane of the selected lead.
// ABOUTME: Refetches the run, the queue, the items and the lead after every action and on an interval; the selected lead is held in state, with no router.
import { useEffect, useState } from 'react'
import { getItems, getLeads, getRun } from '@/api/client'
import { useRemote } from '@/api/useRemote'
import { ItemsSection } from '@/items/ItemsSection'
import { LeadDetailPage } from '@/lead/LeadDetailPage'
import { QueuePage } from '@/queue/QueuePage'

const REFRESH_MILLISECONDS = 5000

function App() {
  const [selectedLeadId, setSelectedLeadId] = useState<string | null>(null)
  const [refresh, setRefresh] = useState(0)
  const refetch = () => setRefresh((count) => count + 1)
  useEffect(() => {
    const timer = setInterval(refetch, REFRESH_MILLISECONDS)
    return () => clearInterval(timer)
  }, [])
  const queue = useRemote('queue', () => Promise.all([getRun(), getLeads(), getItems()]), refresh)

  if (queue.state === 'loading') return <p role="status" className="p-6">Loading the queue</p>
  if (queue.state === 'error') {
    return <p role="alert" className="p-6">{`Could not load the queue: ${queue.message}.`}</p>
  }
  const [run, rows, items] = queue.data
  return (
    <main className="grid gap-8 p-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
      <div className="flex flex-col gap-8">
        <QueuePage
          run={run}
          rows={rows}
          selectedLeadId={selectedLeadId}
          onSelect={setSelectedLeadId}
          onChange={refetch}
        />
        <ItemsSection items={items} onSelect={setSelectedLeadId} />
      </div>
      <aside aria-label="Lead detail">
        {selectedLeadId === null ? (
          <p className="text-sm text-muted-foreground">Select a lead to see its detail.</p>
        ) : (
          <LeadDetailPage leadId={selectedLeadId} refresh={refresh} onChange={refetch} />
        )}
      </aside>
    </main>
  )
}

export default App
