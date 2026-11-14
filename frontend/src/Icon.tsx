// Lucide icons exported from the Ditto V2 Figma file (src/assets/icons). Drawn as a CSS mask so they
// take the text colour, the way the design recolours them with its icon/* variables.
const URLS = import.meta.glob<string>('./assets/icons/*.svg', { eager: true, query: '?url', import: 'default' })

export type IconName =
  | 'arrow-up' | 'bell' | 'bike' | 'book-open' | 'box' | 'cable' | 'check' | 'chevron-down' | 'chevron-right'
  | 'circle-small' | 'cpu' | 'droplet' | 'ellipsis' | 'external-link' | 'hammer' | 'house' | 'image'
  | 'image-plus' | 'lightbulb' | 'loader' | 'log-out' | 'monitor' | 'panel-left' | 'plus' | 'printer'
  | 'rotate-ccw' | 'screw' | 'search' | 'shopping-cart' | 'sprout' | 'square' | 'timer' | 'usb' | 'volume' | 'x'

export function Icon({ name, className = '' }: { name: IconName; className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={`icon ${className}`}
      style={{ maskImage: `url("${URLS[`./assets/icons/${name}.svg`]}")` }}
    />
  )
}

/** A row of 2–4 options (Figma "Segment"): skill level, Assembled/Exploded. */
export function Segmented<T extends string>({
  label,
  options,
  value,
  onChange,
  title,
}: {
  label: string
  options: readonly T[]
  value: T
  onChange: (value: T) => void
  title?: string
}) {
  return (
    <div className="segmented" role="group" aria-label={label} title={title}>
      {options.map((o) => (
        <button key={o} type="button" aria-pressed={o === value} onClick={() => onChange(o)}>
          {o}
        </button>
      ))}
    </div>
  )
}
