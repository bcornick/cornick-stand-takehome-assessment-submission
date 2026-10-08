// ABOUTME: Tests the display formats: values in plain words, a date field as a readable date, and a lead id without the run's seed.
// ABOUTME: The fields are typed objects of the generated API types.
import { describe, expect, it } from 'vitest'
import type { components } from '@/api/types'
import { formatFieldValue, formatValue, shortLeadId } from './format'

type Field = components['schemas']['FactField']

const fields: Field[] = [
  { key: 'property_purchase_date', label: 'Purchase Year', section: 'Property', kind: 'date', options: [] },
  { key: 'zip_code', label: 'Zip code', section: 'Location', kind: 'text', options: [] },
]

describe('formatValue', () => {
  it.each([
    [true, 'Yes'],
    [false, 'No'],
    [null, 'Not provided'],
    [undefined, 'Not provided'],
    [500000, '500000'],
    ['slate', 'slate'],
  ])('reads %s as %s', (value, text) => {
    expect(formatValue(value)).toBe(text)
  })
})

describe('formatFieldValue', () => {
  it('reads the value of a date field as a date', () => {
    expect(formatFieldValue(fields, 'property_purchase_date', '2008-07-15')).toBe('Jul 15, 2008')
  })

  it('leaves the value of any other field as it is', () => {
    expect(formatFieldValue(fields, 'zip_code', '2008-07-15')).toBe('2008-07-15')
    expect(formatFieldValue(fields, 'unlisted', false)).toBe('No')
  })

  it('reads a date field with no value as not provided', () => {
    expect(formatFieldValue(fields, 'property_purchase_date', null)).toBe('Not provided')
  })
})

describe('shortLeadId', () => {
  it.each([
    ['LEAD-00000042-003', 'LEAD-003'],
    ['LEAD-1', 'LEAD-1'],
  ])('shows %s as %s', (id, shown) => {
    expect(shortLeadId(id)).toBe(shown)
  })
})
