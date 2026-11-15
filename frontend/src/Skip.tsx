import { Component, type ReactNode } from 'react'

/** Renders nothing in place of children that throw (a 3D file that 404s), so the rest of the view
 * still shows. Key it by the files it loads: a new key retries. */
export default class Skip extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false }

  static getDerivedStateFromError() {
    return { failed: true }
  }

  render() {
    return this.state.failed ? null : this.props.children
  }
}
