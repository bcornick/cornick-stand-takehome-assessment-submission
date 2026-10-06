// ABOUTME: Vitest setup: adds the jest-dom matchers, unmounts rendered trees after each test, and gives elements the scrollIntoView that jsdom leaves out.
// ABOUTME: Runs before every test file.
import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

Element.prototype.scrollIntoView = () => {}

afterEach(cleanup)
