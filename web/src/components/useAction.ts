// ABOUTME: A hook that runs one async action, holds whether it is busy and the reason it was refused or failed, and tells the page to refetch when the action is done.
// ABOUTME: The action resolves to the reason it was refused, or null when it was accepted; run() reports whether it was accepted.
import { useState } from 'react'

export function useAction(onDone: () => void) {
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)

  async function run(act: () => Promise<string | null>): Promise<boolean> {
    setBusy(true)
    let accepted = false
    try {
      const reason = await act()
      setMessage(reason)
      accepted = reason === null
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error))
    } finally {
      setBusy(false)
      onDone()
    }
    return accepted
  }

  return { busy, message, run }
}
