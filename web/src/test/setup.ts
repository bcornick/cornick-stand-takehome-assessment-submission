// ABOUTME: Vitest setup: adds the jest-dom matchers and unmounts rendered trees after each test.
// ABOUTME: Runs before every test file.
import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

afterEach(cleanup)
