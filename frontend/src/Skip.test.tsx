import { render, screen } from '@testing-library/react'
import { expect, test, vi } from 'vitest'
import Skip from './Skip'

function Missing(): never {
  throw new Error('404 cad/forearm.stl')
}

test('a child that fails to load is skipped, its siblings still render', () => {
  vi.spyOn(console, 'error').mockImplementation(() => {}) // React logs the caught error
  render(
    <>
      <Skip>
        <Missing />
      </Skip>
      <p>case</p>
    </>,
  )
  expect(screen.getByText('case')).toBeTruthy()
})
