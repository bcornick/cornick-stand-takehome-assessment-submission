// ABOUTME: A hook that runs one async load and reports loading, error or ready.
// ABOUTME: The load runs again when the key or the refresh count changes; a refresh keeps the last result on show until the new one arrives, and a result that arrives for an old key or count is dropped.
import { useEffect, useState } from 'react'

type Remote<T> =
  | { state: 'loading' }
  | { state: 'error'; message: string }
  | { state: 'ready'; data: T }

type Settled<T> = { key: string; outcome: { data: T } | { message: string } }

export function useRemote<T>(key: string, load: () => Promise<T>, refresh: number): Remote<T> {
  const [settled, setSettled] = useState<Settled<T> | null>(null)

  useEffect(() => {
    let current = true
    load().then(
      (data) => current && setSettled({ key, outcome: { data } }),
      (error: unknown) =>
        current &&
        setSettled({ key, outcome: { message: error instanceof Error ? error.message : String(error) } }),
    )
    return () => {
      current = false
    }
    // `load` is a fresh closure on each render; the key and the refresh count identify the request.
  }, [key, refresh])

  if (settled === null || settled.key !== key) return { state: 'loading' }
  return 'data' in settled.outcome
    ? { state: 'ready', data: settled.outcome.data }
    : { state: 'error', message: settled.outcome.message }
}
