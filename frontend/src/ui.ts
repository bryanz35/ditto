// Small helpers shared by the screens (kept out of the .tsx files so React fast refresh stays happy).
import type { KeyboardEvent } from 'react'
import type { IconName } from './Icon'

/** Props for a control the design shows but the backend can't serve yet: drawn as in Figma, inert,
 * with a tooltip naming the board task that will connect it. */
export const soon = (task: string | null) => ({
  'aria-disabled': true,
  title: task ? `Not connected yet (${task})` : 'Not connected yet',
  'data-placeholder': task ?? '',
})

/** Enter sends, Shift+Enter adds a line (the composer hint under the Start box). */
export const enterSends = (send: () => void) => (e: KeyboardEvent<HTMLTextAreaElement>) => {
  if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
    e.preventDefault()
    send()
  }
}

export const usd = (v: number | null) => (v === null ? '—' : `$${v.toFixed(2)}`)

const iconFor = (rules: [RegExp, IconName][]) => (text: string) =>
  rules.find(([re]) => re.test(text))?.[1] ?? 'box'

/** Tile icon for a part, from its library id or name. */
export const partIcon = iconFor([
  [/esp32|devkit|arduino|pico/i, 'cpu'],
  [/oled|lcd|display|screen|tft|matrix/i, 'monitor'],
  [/buzzer|speaker/i, 'volume'],
  [/screw/i, 'screw'],
  [/wire|jumper/i, 'cable'],
  [/usb/i, 'usb'],
  [/case|enclosure/i, 'printer'],
])

/** Tile icon for a project in the sidebar, from its title. */
export const projectIcon = iconFor([
  [/plant|soil|garden/i, 'sprout'],
  [/water|drink/i, 'droplet'],
  [/timer|clock|study/i, 'timer'],
  [/bike/i, 'bike'],
  [/door|bell|chime/i, 'bell'],
  [/light|lamp/i, 'lightbulb'],
])
