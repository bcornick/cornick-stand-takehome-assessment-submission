// ABOUTME: Root component of the underwriter surface: the lead list on the left, the open conversation in the centre, the drill-down panel on the right when something is opened, and the demo controls pinned bottom right.
// ABOUTME: Refetches the run, the queue, the items and the cards after every action and on an interval; which conversation and panel are open is held in state, with no router, and the chat tails live in memory.
import { useEffect, useState } from 'react'
import { getItems, getLeads, getProposals, getRun } from '@/api/client'
import { useRemote } from '@/api/useRemote'
import { useChat } from '@/chat/useChat'
import { LeadConversation } from '@/conversation/LeadConversation'
import { QueueConversation } from '@/conversation/QueueConversation'
import { DemoPanel } from '@/demo/DemoPanel'
import { Panel } from '@/panel/Panel'
import { LeadList } from '@/shell/LeadList'
import { QUEUE, type PanelTarget } from '@/surface'

const REFRESH_MILLISECONDS = 5000

function App() {
  const [conversation, setConversation] = useState(QUEUE)
  const [panel, setPanel] = useState<PanelTarget | null>(null)
  const [refresh, setRefresh] = useState(0)
  const refetch = () => setRefresh((count) => count + 1)
  useEffect(() => {
    const timer = setInterval(refetch, REFRESH_MILLISECONDS)
    return () => clearInterval(timer)
  }, [])
  const surface = useRemote(
    'surface',
    () => Promise.all([getRun(), getLeads(), getItems(), getProposals()]),
    refresh,
  )
  const runId = surface.state === 'ready' ? surface.data[0].run_id : null
  const chat = useChat(runId, refetch)

  if (surface.state === 'loading') return <p role="status" className="p-6">Loading the queue</p>
  if (surface.state === 'error') {
    return <p role="alert" className="p-6">{`Could not load the queue: ${surface.message}.`}</p>
  }
  const [run, rows, items, proposals] = surface.data
  const shared = { run, proposals, chat, refresh, onOpen: setPanel, onSelect: setConversation, onChange: refetch }
  return (
    <div className="grid h-screen min-w-[1280px] grid-cols-[280px_minmax(0,1fr)_auto]">
      <LeadList run={run} rows={rows} selected={conversation} onSelect={setConversation} />
      <main className="min-h-0 border-x">
        {conversation === QUEUE ? (
          <QueueConversation items={items} {...shared} />
        ) : (
          <LeadConversation leadId={conversation} {...shared} />
        )}
      </main>
      {panel !== null && (
        <Panel
          target={panel}
          refresh={refresh}
          onOpen={setPanel}
          onClose={() => setPanel(null)}
          onChange={refetch}
        />
      )}
      <DemoPanel run={run} onChange={refetch} />
    </div>
  )
}

export default App
