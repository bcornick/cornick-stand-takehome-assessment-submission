// ABOUTME: A button that runs one action, shows the reason when the action is refused or fails, and tells the page to refetch when the action is done.
// ABOUTME: The action resolves to the reason it was refused, or null when it was accepted.
import { useAction } from './useAction'

type Props = { label: string; act: () => Promise<string | null>; onDone: () => void }

export function ActionButton({ label, act, onDone }: Props) {
  const { busy, message, run } = useAction(onDone)

  return (
    <span className="flex flex-wrap items-center gap-2">
      <button
        type="button"
        disabled={busy}
        onClick={() => run(act)}
        className="rounded-md border bg-primary px-3 py-1.5 text-sm text-primary-foreground disabled:opacity-50"
      >
        {label}
      </button>
      {message !== null && (
        <span role="alert" className="text-sm text-destructive">
          {message}
        </span>
      )}
    </span>
  )
}
