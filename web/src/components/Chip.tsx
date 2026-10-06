// ABOUTME: A citation chip: a small numbered button that opens the drill-down panel on the thing it cites.
// ABOUTME: Its accessible name says what it opens, since the number alone does not.
type Props = { label: string | number; opens: string; onClick: () => void }

export function Chip({ label, opens, onClick }: Props) {
  return (
    <button
      type="button"
      aria-label={opens}
      onClick={onClick}
      className="rounded-full border border-accent px-1.5 font-mono text-xs leading-5 text-accent outline-none hover:bg-accent/10 focus-visible:ring-3 focus-visible:ring-ring/50"
    >
      {label}
    </button>
  )
}
