// ABOUTME: Tests the answer renderer: blank lines make paragraphs, "- " lines make a bulleted list and "1. " lines a numbered one, and a list can follow a paragraph without a blank line.
// ABOUTME: Pure text in, structure out; the markup is the only subject.
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { AnswerText, blocksOf } from './AnswerText'

describe('blocksOf', () => {
  it('splits paragraphs on blank lines and gathers list lines, with or without a blank line before them', () => {
    const answer = "Here's the spread, by state:\n- CA, Sonoma: 2 leads\n- FL, Collier: 3 leads\n\nTwo leads have no state.\n\n1. first\n2. second"
    expect(blocksOf(answer)).toEqual([
      { kind: 'paragraph', lines: ["Here's the spread, by state:"] },
      { kind: 'bullets', items: ['CA, Sonoma: 2 leads', 'FL, Collier: 3 leads'] },
      { kind: 'paragraph', lines: ['Two leads have no state.'] },
      { kind: 'numbers', items: ['first', 'second'] },
    ])
  })

  it('keeps a plain answer as one paragraph', () => {
    expect(blocksOf('Nothing is waiting on you.')).toEqual([{ kind: 'paragraph', lines: ['Nothing is waiting on you.'] }])
  })
})

describe('AnswerText', () => {
  it('renders the bullets as a list and the rest as paragraphs', () => {
    render(<AnswerText answer={'Three leads:\n- 004\n- 007\n\nNone in Europe.'} />)
    expect(screen.getAllByRole('listitem').map((item) => item.textContent)).toEqual(['004', '007'])
    expect(screen.getByText('None in Europe.')).toBeInTheDocument()
  })
})
