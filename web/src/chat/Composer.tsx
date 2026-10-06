// ABOUTME: The one-line message box at the bottom of a conversation.
// ABOUTME: A disabled composer shows the note that says why.
type Props = {
  placeholder: string
  disabled: boolean
  note: string | null
  onSend: (message: string) => void
}

export function Composer({ placeholder, disabled, note }: Props) {
  return (
    <form>
      <input aria-label="Message" placeholder={placeholder} disabled={disabled} />
      {note !== null && <p>{note}</p>}
    </form>
  )
}
