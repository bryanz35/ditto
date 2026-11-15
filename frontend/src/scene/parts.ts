// Procedural part models for the 3D view (ported from the instruction spike).
// Frame: mm, Z up, like the enclosure (backend/contracts/base.py). A model's origin is the centre of
// its layout box, the box assembly.glb draws for the part, so it spans z = -h/2 (floor) to +h/2.
// Looks are approximate: enough to tell the parts apart and to see where each wire goes.
import {
  BoxGeometry,
  CanvasTexture,
  CylinderGeometry,
  EdgesGeometry,
  Group,
  LineBasicMaterial,
  LineSegments,
  Mesh,
  MeshBasicMaterial,
  MeshStandardMaterial,
  PlaneGeometry,
  SphereGeometry,
  SRGBColorSpace,
  Vector2,
  Vector3,
  type BufferGeometry,
} from 'three'
import type { PartDef } from '../contracts'

export type Category = 'mcu' | 'sensor' | 'display' | 'light' | 'input' | 'output' | 'motor' | 'power'

/** The fields of backend/parts/library/*.yaml the 3D view needs: category, board_mm (l, w, h),
 * pins in header order, and whether the part sits outside the case. Keep in step with the YAML. */
export const LIBRARY: Record<
  string,
  {
    cat: Category
    mm: [number, number, number]
    pins: string[]
    external?: true
  }
> = {
  arduino_nano: {
    cat: 'mcu',
    mm: [45, 18, 14],
    pins: [
      'D13',
      '3V3',
      'REF',
      'A0',
      'A1',
      'A2',
      'A3',
      'A4',
      'A5',
      'A6',
      'A7',
      '5V',
      'RST',
      'GND',
      'VIN',
      'D12',
      'D11',
      'D10',
      'D9',
      'D8',
      'D7',
      'D6',
      'D5',
      'D4',
      'D3',
      'D2',
      'GND',
      'RST',
      'D0',
      'D1',
    ],
  },
  arduino_uno_r3: {
    cat: 'mcu',
    mm: [68.6, 53.4, 14],
    pins: [
      'IOREF',
      'RST',
      '3V3',
      '5V',
      'GND',
      'GND',
      'VIN',
      'A0',
      'A1',
      'A2',
      'A3',
      'A4',
      'A5',
      'D13',
      'D12',
      'D11',
      'D10',
      'D9',
      'D8',
      'D7',
      'D6',
      'D5',
      'D4',
      'D3',
      'D2',
      'D1',
      'D0',
      'GND',
      'AREF',
      'SDA',
      'SCL',
    ],
  },
  bme280_breakout: {
    cat: 'sensor',
    mm: [15.5, 11.5, 11],
    pins: ['VCC', 'GND', 'SCL', 'SDA', 'CSB', 'SDO'],
  },
  button_arcade_30mm: { cat: 'input', mm: [33, 33, 40], pins: ['NO', 'COM'] },
  button_tactile_6mm: { cat: 'input', mm: [7.9, 6, 7.8], pins: ['1', '3'] },
  buzzer_passive: {
    cat: 'output',
    mm: [18.5, 15, 12],
    pins: ['SIG', 'MID', 'GND'],
  },
  ds18b20_probe: {
    cat: 'sensor',
    mm: [30, 6, 6],
    pins: ['VDD', 'GND', 'DATA'],
    external: true,
  },
  esp32_devkitc: { cat: 'mcu', mm: [54.3, 27.94, 13.5], pins: [] }, // rows: ESP32_ROWS
  hc_sr04p: {
    cat: 'sensor',
    mm: [45, 20, 15],
    pins: ['VCC', 'TRIG', 'ECHO', 'GND'],
  },
  inmp441: {
    cat: 'sensor',
    mm: [15, 15, 10],
    pins: ['VDD', 'GND', 'SD', 'WS', 'SCK', 'LR'],
  },
  ky040_encoder: {
    cat: 'input',
    mm: [30, 18, 30],
    pins: ['CLK', 'DT', 'SW', 'VCC', 'GND'],
  },
  max98357a: {
    cat: 'output',
    mm: [19.4, 17.8, 18],
    pins: ['LRC', 'BCLK', 'DIN', 'GAIN', 'SD', 'GND', 'Vin'],
  },
  pir_hc_sr501: {
    cat: 'sensor',
    mm: [32, 24, 24.7],
    pins: ['VCC', 'OUT', 'GND'],
  },
  relay_module_1ch: {
    cat: 'output',
    mm: [42, 24, 18.5],
    pins: ['SIG', 'VCC', 'GND'],
  },
  rpi_pico: {
    cat: 'mcu',
    mm: [51, 21, 12.5],
    pins: [
      'GP0',
      'GP1',
      'GND',
      'GP2',
      'GP3',
      'GP4',
      'GP5',
      'GND',
      'GP6',
      'GP7',
      'GP8',
      'GP9',
      'GND',
      'GP10',
      'GP11',
      'GP12',
      'GP13',
      'GND',
      'GP14',
      'GP15',
      'VBUS',
      'VSYS',
      'GND',
      '3V3_EN',
      '3V3',
      'ADC_VREF',
      'GP28',
      'GND',
      'GP27',
      'GP26',
      'RUN',
      'GP22',
      'GND',
      'GP21',
      'GP20',
      'GP19',
      'GP18',
      'GND',
      'GP17',
      'GP16',
    ],
  },
  servo_mg90s: {
    cat: 'motor',
    mm: [22.8, 12.2, 28.5],
    pins: ['GND', 'VCC', 'PWM'],
    external: true,
  },
  servo_mg996r: {
    cat: 'motor',
    mm: [40.7, 19.7, 42.9],
    pins: ['GND', 'VCC', 'PWM'],
    external: true,
  },
  servo_sg90: {
    cat: 'motor',
    mm: [23, 12.2, 29],
    pins: ['GND', 'VCC', 'PWM'],
    external: true,
  },
  soil_moisture_capacitive: {
    cat: 'sensor',
    mm: [98, 23, 7],
    pins: ['GND', 'VCC', 'AOUT'],
    external: true,
  },
  speaker_40mm_4ohm: { cat: 'output', mm: [40, 40, 21], pins: ['+', '-'] },
  ssd1306_096_i2c: {
    cat: 'display',
    mm: [28, 28, 12],
    pins: ['GND', 'VCC', 'SCL', 'SDA'],
  },
  stepper_28byj48: {
    cat: 'motor',
    mm: [42, 31, 29],
    pins: ['IN1', 'IN2', 'IN3', 'IN4', 'VCC', 'GND'],
    external: true,
  },
  vibration_motor_module: {
    cat: 'output',
    mm: [30, 22, 8],
    pins: ['SIG', 'VCC', 'GND'],
  },
  ws2812b_ring_12: {
    cat: 'light',
    mm: [36.8, 36.8, 6.7],
    pins: ['VCC', 'GND', 'DIN', 'DOUT'],
  },
  xiao_esp32s3_sense: {
    cat: 'mcu',
    mm: [21, 17.8, 21],
    pins: [
      'GPIO1',
      'GPIO2',
      'GPIO3',
      'GPIO4',
      'GPIO5',
      'GPIO6',
      'GPIO43',
      '5V',
      'GND',
      '3V3',
      'GPIO9',
      'GPIO8',
      'GPIO7',
      'GPIO44',
    ],
  },
}

// ESP32-DevKitC V4, the two 19-pin rows from the antenna end (Espressif pin layout).
const ESP32_ROWS = [
  [
    '3V3',
    'EN',
    'GPIO36',
    'GPIO39',
    'GPIO34',
    'GPIO35',
    'GPIO32',
    'GPIO33',
    'GPIO25',
    'GPIO26',
    'GPIO27',
    'GPIO14',
    'GPIO12',
    'GND',
    'GPIO13',
    'SD2',
    'SD3',
    'CMD',
    '5V',
  ],
  [
    'GND',
    'GPIO23',
    'GPIO22',
    'TX',
    'RX',
    'GPIO21',
    'GND',
    'GPIO19',
    'GPIO18',
    'GPIO5',
    'GPIO17',
    'GPIO16',
    'GPIO4',
    'GPIO0',
    'GPIO2',
    'GPIO15',
    'SD1',
    'SD0',
    'CLK',
  ],
]

/** Shapes on top of the PCB. `at` is a fraction of the footprint (-0.5..0.5 along x and y); sizes
 * are mm, clamped to the footprint. The model's header sits on its +y edge (boards: rows on ±y). */
type Shape =
  | {
      box: [number, number, number]
      at: [number, number]
      color: string
      metal?: number
      on?: number
    }
  | {
      cyl: [number, number]
      at: [number, number]
      color: string
      metal?: number
      on?: number
      /** Lying along x or y instead of standing; `on` is then its underside. */
      axis?: 'x' | 'y'
      /** Lights up with the LEDs once the code runs. */
      glow?: true
    }
  | { screen: [number, number]; at: [number, number] }
  | { led: [number, number, number]; at: [number, number]; color: string }
  | { dome: number; at: [number, number]; color: string; on?: number; glow?: true }
  | { ring: [number, number]; leds: number }

interface Look {
  pcb: string | null
  /** Height of the PCB's underside above the floor (posts or headers below it). */
  lift?: number
  /** The part size (l, w, h) the shapes are drawn for: boxes and cylinders then scale to the part's box. */
  mm?: [number, number, number]
  shapes: Shape[]
}

const SILVER = '#c9ccd2'
// One servo, drawn at SG90 size and scaled to each servo's box.
const servo = (color: string): Look => ({
  pcb: null,
  mm: [23, 12.2, 29],
  shapes: [
    { box: [23, 12.2, 22], at: [0, 0], color },
    { box: [32, 12.2, 2.5], at: [0, 0], color, on: 15 },
    { cyl: [2.5, 5], at: [-0.25, 0], color: '#f2f2f2', on: 22 },
    { box: [16, 4, 1.5], at: [-0.25, 0], color: '#f2f2f2', on: 27 },
  ],
})
const LOOKS: Record<string, Look> = {
  esp32_devkitc: {
    pcb: '#23262d',
    lift: 5,
    shapes: [
      { box: [23, 18, 0.8], at: [0.27, 0], color: '#2f323a' },
      {
        box: [17.6, 15.8, 3.1],
        at: [0.22, 0],
        color: SILVER,
        metal: 0.6,
        on: 0.8,
      },
      { box: [6, 7.5, 3], at: [-0.45, 0], color: SILVER, metal: 0.6 },
      { box: [3.5, 3, 1.6], at: [-0.37, 0.31], color: '#f2f2f2' },
      { box: [3.5, 3, 1.6], at: [-0.37, -0.31], color: '#f2f2f2' },
      { box: [5, 5, 1.4], at: [-0.25, -0.1], color: '#141414' },
      { led: [1.6, 1, 0.8], at: [-0.31, 0.15], color: '#ff4d4d' },
    ],
  },
  arduino_uno_r3: {
    pcb: '#0f6f93',
    lift: 3,
    shapes: [
      { box: [35, 7.5, 3.5], at: [0.05, -0.18], color: '#141414' },
      { box: [16, 12, 11], at: [-0.42, 0.2], color: SILVER, metal: 0.6 },
      { box: [13, 9, 11], at: [-0.42, -0.3], color: '#141414' },
      { led: [1.6, 1, 0.8], at: [-0.2, 0.3], color: '#55ff55' },
    ],
  },
  arduino_nano: {
    pcb: '#1d5fa8',
    lift: 4,
    shapes: [
      { box: [7, 7, 1.2], at: [0.05, 0], color: '#141414' },
      { box: [8, 7.5, 4], at: [-0.42, 0], color: SILVER, metal: 0.6 },
      { led: [1.6, 1, 0.8], at: [0.25, 0.1], color: '#55ff55' },
    ],
  },
  rpi_pico: {
    pcb: '#2c7a3f',
    lift: 4,
    shapes: [
      { box: [7, 7, 1], at: [0.05, 0], color: '#141414' },
      { box: [8, 7.5, 3], at: [-0.45, 0], color: SILVER, metal: 0.6 },
      { box: [3.5, 3, 1.4], at: [-0.25, 0.25], color: '#f2f2f2' },
      { led: [1.6, 1, 0.8], at: [-0.32, -0.2], color: '#55ff55' },
    ],
  },
  xiao_esp32s3_sense: {
    pcb: '#202227',
    lift: 4,
    shapes: [
      { box: [15, 12, 2.5], at: [0.1, 0], color: SILVER, metal: 0.6 },
      { box: [9, 7, 3.2], at: [-0.4, 0], color: SILVER, metal: 0.6 },
      { box: [8, 8, 7], at: [0.1, 0], color: '#141414', on: 2.5 },
      { cyl: [2, 1.5], at: [0.1, 0], color: '#3b3440', on: 9.5 },
    ],
  },
  ssd1306_096_i2c: {
    pcb: '#1f4e9c',
    lift: 2,
    shapes: [
      { box: [26, 16, 1.4], at: [0, -0.07], color: '#0b0e13' },
      { screen: [22, 11], at: [0, -0.07] },
      { box: [9, 2.6, 0.3], at: [0, -0.4], color: '#c8a35a' },
    ],
  },
  bme280_breakout: {
    pcb: '#6a3fa0',
    lift: 2,
    shapes: [
      { box: [2.6, 2.6, 0.9], at: [0, -0.2], color: SILVER, metal: 0.7 },
      { box: [1.8, 1, 0.6], at: [-0.3, -0.3], color: '#c9a35a' },
    ],
  },
  buzzer_passive: {
    pcb: '#1f5e3a',
    lift: 2,
    shapes: [
      { cyl: [5.5, 8], at: [0, -0.12], color: '#1a1a1a' },
      { cyl: [1, 8.1], at: [0, -0.12], color: '#5a5a5a' },
    ],
  },
  soil_moisture_capacitive: {
    pcb: '#26272c',
    shapes: [
      { box: [9, 9, 1.4], at: [0, 0.36], color: '#2a2a2e' },
      { box: [23, 2.5, 0.1], at: [0, -0.05], color: '#e8e8e8' },
      { box: [5, 5, 1.2], at: [0.2, 0.3], color: '#111' },
    ],
  },
  ds18b20_probe: {
    pcb: null,
    shapes: [
      { cyl: [3, 6], at: [0, -0.2], color: '#b9bec6', metal: 0.8 },
      { box: [4, 14, 4], at: [0, 0.2], color: '#141414' },
    ],
  },
  hc_sr04p: {
    pcb: '#1d5fa8',
    lift: 2,
    shapes: [
      { cyl: [8, 12], at: [-0.28, -0.08], color: SILVER, metal: 0.6 },
      { cyl: [8, 12], at: [0.28, -0.08], color: SILVER, metal: 0.6 },
      { cyl: [6, 12.2], at: [-0.28, -0.08], color: '#202020' },
      { cyl: [6, 12.2], at: [0.28, -0.08], color: '#202020' },
    ],
  },
  pir_hc_sr501: {
    pcb: '#1f6b3a',
    lift: 2,
    shapes: [
      { box: [23, 23, 3], at: [0, -0.05], color: '#e8e8e8' },
      { dome: 11, at: [0, -0.05], color: '#f4f4f4' },
    ],
  },
  inmp441: {
    pcb: '#5b3c8c',
    lift: 2,
    shapes: [{ cyl: [3.5, 1.2], at: [0, -0.1], color: SILVER, metal: 0.7 }],
  },
  ky040_encoder: {
    pcb: '#1d5fa8',
    lift: 2,
    shapes: [
      { box: [12, 13, 6], at: [-0.1, -0.05], color: SILVER, metal: 0.6 },
      { cyl: [3, 15], at: [-0.1, -0.05], color: '#b0b4ba', metal: 0.6, on: 6 },
    ],
  },
  button_arcade_30mm: {
    pcb: null,
    shapes: [
      { cyl: [15, 10], at: [0, 0], color: '#141414' },
      { cyl: [12, 8], at: [0, 0], color: '#e5484d', on: 10 },
    ],
  },
  button_tactile_6mm: {
    pcb: null,
    shapes: [
      { box: [6, 6, 3.5], at: [0, 0], color: '#141414' },
      { cyl: [1.8, 2], at: [0, 0], color: '#2a2a2a', on: 3.5 },
    ],
  },
  max98357a: {
    pcb: '#5b3c8c',
    lift: 2,
    shapes: [
      { box: [4, 4, 1], at: [0, -0.15], color: '#141414' },
      { box: [7, 6, 5], at: [0, -0.35], color: '#18c08b' },
    ],
  },
  speaker_40mm_4ohm: {
    pcb: null,
    shapes: [
      { cyl: [20, 6], at: [0, 0], color: '#18181b' },
      { cyl: [15, 6.3], at: [0, 0], color: '#3f3f46' },
      { cyl: [5, 6.6], at: [0, 0], color: SILVER, metal: 0.6 },
    ],
  },
  servo_sg90: servo('#2563eb'),
  servo_mg90s: servo('#1c1c1f'),
  servo_mg996r: servo('#1c1c1f'),
  // Kiatronics drawing: a 28 mm can 19 mm tall with its ears on top, the blue wire cover on +y (the
  // header side) and the shaft 8 mm off-centre opposite it. The can's centre is 1.5 mm below the box's.
  stepper_28byj48: {
    pcb: null,
    shapes: [
      { cyl: [14, 19], at: [0, -0.048], color: SILVER, metal: 0.6 },
      { box: [42, 7, 0.8], at: [0, -0.048], color: SILVER, metal: 0.6, on: 18.2 },
      { box: [14.6, 6, 17], at: [0, 0.4], color: '#2f6fd6' },
      { cyl: [4.5, 1.5], at: [0, -0.306], color: SILVER, metal: 0.6, on: 19 },
      { cyl: [2.5, 8.5], at: [0, -0.306], color: '#d9c37c', metal: 0.7, on: 20.5 },
    ],
  },
  relay_module_1ch: {
    pcb: '#1d5fa8',
    lift: 2,
    shapes: [
      { box: [19, 15.5, 15], at: [0.12, -0.08], color: '#2b6cdf' },
      { box: [8, 15, 10], at: [-0.38, -0.08], color: '#1fa37a' },
      { led: [1.6, 1, 0.8], at: [-0.15, 0.3], color: '#ff4d4d' },
    ],
  },
  vibration_motor_module: {
    pcb: '#1d5fa8',
    lift: 2,
    shapes: [{ cyl: [5, 2.7], at: [0.15, -0.1], color: SILVER, metal: 0.7 }],
  },
  ws2812b_ring_12: { pcb: null, shapes: [{ ring: [18.4, 12.5], leds: 12 }] },
}

// A plain breakout: chip, passives, LED. Drawn true size whatever the box.
const MODULE: Look = {
  pcb: '#1f5e8a',
  lift: 2,
  shapes: [
    { box: [5, 5, 1.2], at: [0, -0.12], color: '#141414' },
    { box: [2, 1.25, 0.6], at: [-0.28, -0.12], color: '#c9a35a' },
    { box: [2, 1.25, 0.6], at: [0.28, -0.12], color: '#c9a35a' },
    { box: [1.6, 0.8, 0.5], at: [0, -0.38], color: '#3f3f46' },
    { led: [1.6, 1, 0.8], at: [0.32, 0.18], color: '#55ff55' },
  ],
}

// A part with no look of its own that no name matches (a custom part, or one added to the library
// later) gets its category's.
const BY_CATEGORY: Record<Category, Look> = {
  mcu: {
    pcb: '#1d6b8f',
    lift: 4,
    shapes: [
      { box: [10, 10, 1.4], at: [0.05, 0], color: '#141414' },
      { box: [7, 7, 3], at: [-0.43, 0], color: SILVER, metal: 0.6 },
    ],
  },
  sensor: {
    pcb: '#2563a8',
    lift: 2,
    shapes: [{ box: [3, 3, 1], at: [0, -0.2], color: '#141414' }],
  },
  display: {
    pcb: '#1f4e9c',
    lift: 2,
    shapes: [
      { box: [24, 14, 1.4], at: [0, -0.07], color: '#0b0e13' },
      { screen: [20, 10], at: [0, -0.07] },
    ],
  },
  light: {
    pcb: '#222326',
    lift: 2,
    shapes: [
      { led: [5, 5, 1.6], at: [-0.25, -0.1], color: '#f5f5f5' },
      { led: [5, 5, 1.6], at: [0.25, -0.1], color: '#f5f5f5' },
    ],
  },
  input: MODULE,
  output: MODULE,
  // most custom motors are servos (an MG996R the library lacks)
  motor: servo('#3f3f46'),
  power: MODULE,
}

const BLACK = '#18181b'
const BLUE_PCB = '#1d5fa8'
const BRASS = '#d9c37c'
const TERMINAL = '#2563eb'
export type PartLook = NonNullable<PartDef['look']>

/** The looks a custom part can borrow (PartDef.look, else by name: NAMED): common parts the library
 * lacks, drawn at a typical size (`mm`) and scaled to the part's box, plus a few library parts'.
 * Preview: /parts.html. */
export const GENERIC: Record<PartLook, Look> = {
  pot_rotary: {
    pcb: null,
    mm: [17, 17, 25],
    shapes: [
      { cyl: [6.5, 7], at: [0, -0.12], color: SILVER, metal: 0.6 },
      { cyl: [3.5, 4], at: [0, -0.12], color: SILVER, metal: 0.6, on: 7 },
      { cyl: [3, 6], at: [0, -0.12], color: '#b0b4ba', metal: 0.6, on: 11 },
      { cyl: [6.5, 7.7], at: [0, -0.12], color: BLACK, on: 17 },
      { box: [1, 4, 0.3], at: [0, -0.3], color: '#f2f2f2', on: 24.7 },
    ],
  },
  pot_slide: {
    pcb: BLUE_PCB,
    lift: 2,
    mm: [60, 12, 15],
    shapes: [
      { box: [52, 8, 6], at: [0, -0.1], color: BLACK },
      { box: [44, 1.2, 0.2], at: [0, -0.1], color: '#050505', on: 6 },
      { box: [2.5, 1, 2], at: [0.12, -0.1], color: SILVER, metal: 0.6, on: 6 },
      { box: [5, 8, 3.4], at: [0.12, -0.1], color: '#e4e4e7', on: 8 },
    ],
  },
  joystick: {
    pcb: BLUE_PCB,
    lift: 2,
    mm: [34, 26, 32],
    shapes: [
      { box: [20, 20, 10], at: [0, -0.1], color: BLACK },
      { dome: 8, at: [0, -0.1], color: '#27272a', on: 10 },
      { cyl: [2, 8], at: [0, -0.1], color: '#3f3f46', on: 16 },
      { cyl: [7, 4.4], at: [0, -0.1], color: BLACK, on: 24 },
    ],
  },
  servo: servo('#1c1c1f'),
  dc_motor: {
    pcb: null,
    mm: [38, 20, 20],
    shapes: [
      { cyl: [10, 25], axis: 'x', at: [-0.05, 0], color: SILVER, metal: 0.6 },
      { cyl: [8, 3], axis: 'x', at: [-0.42, 0], color: '#e8e8e8', on: 1.7 },
      { box: [1.5, 0.4, 4], at: [-0.44, 0.2], color: BRASS, metal: 0.7, on: 15 },
      { box: [1.5, 0.4, 4], at: [-0.44, -0.2], color: BRASS, metal: 0.7, on: 15 },
      { cyl: [3, 2], axis: 'x', at: [0.305, 0], color: SILVER, metal: 0.6, on: 6.7 },
      { cyl: [1, 8], axis: 'x', at: [0.4, 0], color: BRASS, metal: 0.7, on: 8.7 },
    ],
  },
  tt_gearmotor: {
    pcb: null,
    mm: [64, 22.5, 19],
    shapes: [
      { box: [36, 18, 19], at: [0.203, 0], color: '#f2c230' },
      { cyl: [9.5, 22], axis: 'x', at: [-0.25, 0], color: SILVER, metal: 0.6 },
      { cyl: [8, 4], axis: 'x', at: [-0.453, 0], color: BLACK, on: 1.5 },
      { cyl: [2.7, 22.5], axis: 'y', at: [0.375, 0], color: '#f2f2f2', on: 7 },
    ],
  },
  n20_gearmotor: {
    pcb: null,
    mm: [34, 12, 10],
    shapes: [
      { cyl: [5, 15], axis: 'x', at: [-0.22, 0], color: SILVER, metal: 0.6 },
      { cyl: [4.5, 2], axis: 'x', at: [-0.47, 0], color: BLACK, on: 0.5 },
      { box: [9, 12, 10], at: [0.132, 0], color: '#a1a5ad', metal: 0.6 },
      { cyl: [1.5, 8], axis: 'x', at: [0.382, 0], color: SILVER, metal: 0.6, on: 3.5 },
    ],
  },
  capacitor: {
    pcb: null,
    mm: [13, 13, 25],
    shapes: [
      { cyl: [5, 1.5], at: [0, -0.1], color: '#111' },
      { cyl: [5, 23], at: [0, -0.1], color: '#1f2a44', on: 1.5 },
      { box: [0.4, 3, 23], at: [0.385, -0.1], color: '#cbd5e1', on: 1.5 },
      { cyl: [4.8, 0.4], at: [0, -0.1], color: SILVER, metal: 0.6, on: 24.5 },
      { box: [6, 0.4, 0.1], at: [0, -0.1], color: '#71717a', on: 24.9 },
      { box: [0.4, 6, 0.1], at: [0, -0.1], color: '#71717a', on: 24.9 },
    ],
  },
  barrel_jack: {
    pcb: BLUE_PCB,
    lift: 2,
    mm: [30, 20, 15],
    shapes: [
      { box: [14, 9, 11], at: [-0.26, -0.15], color: BLACK },
      { cyl: [3.2, 0.6], axis: 'x', at: [-0.495, -0.15], color: '#050505', on: 2.3 },
      { cyl: [1, 0.8], axis: 'x', at: [-0.5, -0.15], color: SILVER, metal: 0.6, on: 4.5 },
      { box: [8, 7.5, 9], at: [0.3, -0.15], color: '#1fa37a' },
      { cyl: [1.4, 0.4], at: [0.23, -0.15], color: SILVER, metal: 0.6, on: 9 },
      { cyl: [1.4, 0.4], at: [0.37, -0.15], color: SILVER, metal: 0.6, on: 9 },
    ],
  },
  buck_module: {
    pcb: BLUE_PCB,
    lift: 2,
    mm: [43, 21, 14],
    shapes: [
      { box: [12, 12, 7], at: [0.05, 0.05], color: '#232326' },
      { cyl: [4, 10], at: [-0.38, -0.08], color: BLACK },
      { cyl: [4, 10], at: [0.38, -0.08], color: BLACK },
      { cyl: [3.8, 0.3], at: [-0.38, -0.08], color: SILVER, metal: 0.6, on: 10 },
      { cyl: [3.8, 0.3], at: [0.38, -0.08], color: SILVER, metal: 0.6, on: 10 },
      { box: [9, 9, 4.4], at: [-0.18, 0.1], color: '#141414' },
      { box: [9.5, 4.5, 9.5], at: [0.16, -0.36], color: '#2b6cdf' },
      { cyl: [1.1, 0.6], at: [0.23, -0.36], color: BRASS, metal: 0.7, on: 9.5 },
    ],
  },
  driver_l298n: {
    pcb: '#c0262d',
    lift: 2,
    mm: [43, 43, 27],
    shapes: [
      { box: [23, 3, 23], at: [0, 0.15], color: '#1a1a1a', metal: 0.3 },
      ...[-0.2, -0.1, 0, 0.1, 0.2].map((x) => ({
        box: [1.2, 6, 20] as [number, number, number],
        at: [x, 0.045] as [number, number],
        color: '#1a1a1a',
        metal: 0.3,
      })),
      { box: [20, 4, 10], at: [0, 0.24], color: '#141414' },
      { box: [7.5, 10, 10], at: [-0.41, 0.05], color: TERMINAL },
      { box: [7.5, 10, 10], at: [0.41, 0.05], color: TERMINAL },
      { box: [15, 7.5, 10], at: [0, -0.4], color: TERMINAL },
      { cyl: [4, 11], at: [-0.25, -0.22], color: BLACK },
      { cyl: [4, 11], at: [0.25, -0.22], color: BLACK },
      { led: [1.6, 1, 0.8], at: [0.15, -0.3], color: '#ff4d4d' },
    ],
  },
  driver_small: {
    pcb: '#5b3c8c',
    lift: 2,
    mm: [21, 19, 10],
    shapes: [
      { box: [6.5, 5, 1.2], at: [0, -0.1], color: '#141414' },
      { box: [2, 1.2, 1], at: [-0.3, -0.25], color: '#c9a35a' },
      { box: [2, 1.2, 1], at: [0.3, -0.25], color: '#c9a35a' },
      { box: [15, 2.54, 2.5], at: [0, -0.43], color: '#18191b' },
      { led: [1.6, 1, 0.8], at: [0.32, 0.1], color: '#ff4d4d' },
    ],
  },
  driver_uln2003: {
    pcb: '#1f6b3a',
    lift: 2,
    mm: [35, 32, 15],
    shapes: [
      { box: [20, 7, 3.5], at: [-0.05, -0.05], color: '#141414' },
      { box: [13, 6, 7], at: [0, -0.38], color: '#f2f2f2' },
      ...[0.2, 0.07, -0.06, -0.19].map((y) => ({
        cyl: [1.5, 4] as [number, number],
        at: [0.4, y] as [number, number],
        color: '#ff4d4d',
        glow: true as const,
      })),
    ],
  },
  battery_holder: {
    pcb: null,
    mm: [58, 31, 16],
    shapes: [
      { box: [58, 31, 1.5], at: [0, 0], color: BLACK },
      { box: [58, 1.5, 9], at: [0, 0.475], color: BLACK },
      { box: [58, 1.5, 9], at: [0, -0.475], color: BLACK },
      { box: [2, 31, 12], at: [-0.483, 0], color: BLACK },
      { box: [2, 31, 12], at: [0.483, 0], color: BLACK },
      { cyl: [7, 50], axis: 'x', at: [-0.01, -0.235], color: '#2563eb', on: 1.5 },
      { cyl: [7, 50], axis: 'x', at: [0.01, 0.235], color: '#2563eb', on: 1.5 },
      { cyl: [2.5, 1.5], axis: 'x', at: [0.44, -0.235], color: SILVER, metal: 0.6, on: 6 },
      { cyl: [2.5, 1.5], axis: 'x', at: [-0.44, 0.235], color: SILVER, metal: 0.6, on: 6 },
    ],
  },
  switch_rocker: {
    pcb: null,
    mm: [21, 15, 16],
    shapes: [
      { box: [19, 13, 10], at: [0, -0.05], color: BLACK },
      { box: [21, 15, 2], at: [0, 0], color: BLACK, on: 10 },
      { box: [8, 9.5, 4], at: [-0.2, -0.05], color: '#e5484d', on: 12 },
      { box: [8, 9.5, 2.5], at: [0.2, -0.05], color: '#e5484d', on: 12 },
    ],
  },
  led_5mm: {
    pcb: null,
    mm: [6, 6, 9],
    shapes: [
      { cyl: [2.9, 1], at: [0, -0.1], color: '#ef4444', glow: true },
      { cyl: [2.5, 5], at: [0, -0.1], color: '#ef4444', glow: true, on: 1 },
      { dome: 2.5, at: [0, -0.1], color: '#ef4444', glow: true, on: 6 },
    ],
  },
  ldr_module: {
    pcb: BLUE_PCB,
    lift: 2,
    mm: [32, 14, 10],
    shapes: [
      { cyl: [0.3, 3], at: [-0.43, -0.1], color: SILVER, metal: 0.6 },
      { cyl: [0.3, 3], at: [-0.37, -0.1], color: SILVER, metal: 0.6 },
      { cyl: [2.6, 2], at: [-0.4, -0.1], color: '#c08a3e', on: 3 },
      { box: [3, 0.4, 0.1], at: [-0.4, -0.1], color: '#7a4a1a', on: 5 },
      { box: [6.5, 6.5, 4.5], at: [0.05, -0.1], color: '#2b6cdf' },
      { cyl: [1.2, 0.5], at: [0.05, -0.1], color: '#f2f2f2', on: 4.5 },
      { box: [5, 4, 1.5], at: [0.32, -0.1], color: '#141414' },
      { led: [1.6, 1, 0.8], at: [0.2, 0.3], color: '#ff4d4d' },
    ],
  },
  relay_module_1ch: LOOKS.relay_module_1ch,
  stepper_28byj48: LOOKS.stepper_28byj48,
  ky040_encoder: LOOKS.ky040_encoder,
  button_tactile_6mm: LOOKS.button_tactile_6mm,
  button_arcade_30mm: LOOKS.button_arcade_30mm,
  buzzer_passive: LOOKS.buzzer_passive,
  speaker_40mm_4ohm: LOOKS.speaker_40mm_4ohm,
}

// Which look a custom part with no `look` borrows, by name. First match wins, so specific names come
// before general ones ("motor driver" before "motor", "slide pot" before "pot").
const NAMED: [RegExp, PartLook][] = [
  [/\brelay\b/, 'relay_module_1ch'],
  [/\bl298n?\b/, 'driver_l298n'],
  [/\buln2003\w*\b/, 'driver_uln2003'],
  [/\b(drv88\d\d|tb6612\w*|a4988|l9110s?|motor driver|h bridge)\b/, 'driver_small'],
  [/\b(buck|boost|step (up|down)|lm2596\w*|mt3608|xl6009|dc dc)\b/, 'buck_module'],
  [/\b(servo|sg90|mg90s?|mg99[56]r?)\b/, 'servo'],
  [/\b(stepper|28byj\w*|nema ?\d+)\b/, 'stepper_28byj48'],
  [/\b(n20|micro (metal )?gear\w*)\b/, 'n20_gearmotor'],
  [/\b(tt|gear ?motor|gearbox)\b/, 'tt_gearmotor'],
  [/\bmotors?\b/, 'dc_motor'],
  [/\b(joystick|thumb ?stick|ky 023)\b/, 'joystick'],
  [/\b(rotary )?encoder\b/, 'ky040_encoder'],
  [/\b(slide pot\w*|slider|fader)\b/, 'pot_slide'],
  [/\b(pot|potentiometer|trimmer|trim ?pot)\b/, 'pot_rotary'],
  [/\barcade\b/, 'button_arcade_30mm'],
  [/\b(button|push ?button|tactile)\b/, 'button_tactile_6mm'],
  [/\b(buzzer|piezo)\b/, 'buzzer_passive'],
  [/\bspeaker\b/, 'speaker_40mm_4ohm'],
  [/^(?!.*\b(module|board|breakout|mosfet|transistor)\b).*\b(switch|rocker|toggle)\b/, 'switch_rocker'],
  [/\b(capacitor|electrolytic|\d+ ?uf)\b/, 'capacitor'],
  [/\b(battery|batteries|18650|aaa?|lipo|li ion)\b/, 'battery_holder'],
  [/\b(barrel|dc jack|power jack|psu|power supply|wall (supply|adapter|wart))\b/, 'barrel_jack'],
  [/\b(ldr|photoresistor|photocell)\b/, 'ldr_module'],
  [/^(?!.*\b(strip|matrix|ring|module|board|breakout|panel|bar|neopixel|ws28\w*)\b).*\bleds?\b/, 'led_5mm'],
]

/** The look a custom part borrows, from its id and its name up to the first bracket, comma or "with":
 * "DC wall supply with barrel jack (servo rail)" is a supply, not a servo. Null when nothing matches. */
export const lookFor = (id: string, name: string): PartLook | null => {
  const text = `${id} ${name.split(/[(,;]| with /i)[0]}`.toLowerCase().replace(/[^a-z0-9]+/g, ' ')
  return NAMED.find(([re]) => re.test(text))?.[1] ?? null
}

type Custom = { name: string; look?: PartLook | null }

/** A library part's own look; a custom part's `look`, else one its name suggests; else its category's. */
export const lookOf = (partId: string, category: Category, custom?: Custom): Look => {
  // boards and displays keep their category's look: "XIAO with RGB LED" is not an LED
  const borrowed =
    category === 'mcu' || category === 'display' ? null : (custom?.look ?? lookFor(partId, custom?.name ?? ''))
  return LOOKS[partId] ?? (borrowed ? GENERIC[borrowed] : undefined) ?? BY_CATEGORY[category]
}

export const categoryOf = (partId: string): Category => LIBRARY[partId]?.cat ?? 'sensor'

/** Where the part's header pins are, in header order: library order, then any extra pin the wiring uses. */
export const pinsOf = (partId: string, used: string[]) => {
  const pins = [...(LIBRARY[partId]?.pins ?? [])]
  for (const p of used) if (!pins.includes(p)) pins.push(p)
  return pins
}

export interface PartModel {
  root: Group
  /** Pin tips, where a jumper wire's housing slides on, in root (layout box) coordinates. */
  pins: { name: string; at: Vector3 }[]
  /** The USB socket's mouth and the direction a plug comes from (boards only). */
  usb: { at: Vector3; dir: Vector3 } | null
  /** Every surface material, for the highlight glow. */
  mats: MeshStandardMaterial[]
  /** 'off', 'upload' (with progress 0..1) or 'on': screens draw, LEDs light. */
  setPower: (state: 'off' | 'upload' | 'on', progress?: number) => void
}

const EDGES = new LineBasicMaterial({
  color: '#09090b',
  transparent: true,
  opacity: 0.45,
})
const PITCH = 2.54
const PIN_UP = 3.5 // pin above its plastic strip
const STRIP = 2.5

function drawScreen(ctx: CanvasRenderingContext2D, state: 'off' | 'upload' | 'on', p: number) {
  ctx.fillStyle = '#05080c'
  ctx.fillRect(0, 0, 256, 128)
  if (state === 'off') return
  ctx.fillStyle = '#bfe9ff'
  ctx.strokeStyle = '#bfe9ff'
  ctx.textAlign = 'center'
  if (state === 'upload') {
    ctx.font = 'bold 22px monospace'
    ctx.fillText('UPLOADING', 128, 48)
    ctx.lineWidth = 3
    ctx.strokeRect(28, 66, 200, 20)
    ctx.fillRect(32, 70, 192 * p, 12)
    ctx.font = 'bold 16px monospace'
    ctx.fillText(`${Math.round(p * 100)}%`, 128, 112)
  } else {
    ctx.font = 'bold 16px monospace'
    ctx.fillText('DITTO', 128, 26)
    ctx.font = 'bold 54px monospace'
    ctx.fillText('READY', 128, 88)
    ctx.fillRect(48, 106, 160, 4)
  }
}

/**
 * Builds a part to fill a layout box of `size` (x, y, z mm). `toward` is the direction, in the box's
 * frame, of the board the part wires to (or, for the board itself, of the nearest case wall): the
 * header turns to face it, and a board turns its USB socket to it. `custom`: a custom part's entry.
 */
export function buildPart(
  partId: string,
  category: Category,
  size: Vector3,
  toward: Vector2,
  pinNames: string[],
  custom?: Custom,
): PartModel {
  const look = lookOf(partId, category, custom)
  const isBoard = category === 'mcu'
  const mats: MeshStandardMaterial[] = []
  const std = (color: string, metal = 0) => {
    const m = new MeshStandardMaterial({
      color,
      roughness: metal ? 0.35 : 0.7,
      metalness: metal,
    })
    mats.push(m)
    return m
  }
  const add = (
    parent: Group,
    geo: BufferGeometry,
    m: MeshStandardMaterial | MeshBasicMaterial,
    at: [number, number, number],
    edges = true,
  ) => {
    const mesh = new Mesh(geo, m)
    mesh.position.set(...at)
    if (edges) mesh.add(new LineSegments(new EdgesGeometry(geo, 28), EDGES))
    parent.add(mesh)
    return mesh
  }
  const zcyl = (r: number, h: number, seg = 28) => new CylinderGeometry(r, r, h, seg).rotateX(Math.PI / 2)

  // Which way the model turns: 0, 90, 180 or 270° about z. The canonical model has its header on
  // +y (a board: rows on ±y, USB at -x). Turning by 90 or 270 swaps the footprint's sides.
  const turns = [0, 1, 2, 3]
  const footprint = (q: number) => (q % 2 ? [size.y, size.x] : [size.x, size.y])
  const normal = (q: number) => [new Vector2(0, 1), new Vector2(-1, 0), new Vector2(0, -1), new Vector2(1, 0)][q]
  let quarter: number
  if (isBoard) {
    const long = size.x >= size.y ? [0, 2] : [1, 3]
    // the USB end (-x canonical, which is -normal(q) turned a further 90°) faces `toward`
    const usbDir = (q: number) => normal((q + 1) % 4)
    quarter = long.sort((a, b) => usbDir(b).dot(toward) - usbDir(a).dot(toward))[0]
  } else {
    const fits = (q: number) => pinNames.length * PITCH <= footprint(q)[0] - 1
    const ok = turns.filter(fits)
    const pool = ok.length ? ok : [size.x >= size.y ? 0 : 1, size.x >= size.y ? 2 : 3]
    quarter = pool.sort((a, b) => normal(b).dot(toward) - normal(a).dot(toward))[0]
  }
  const [a, b] = footprint(quarter)
  const h = size.z
  const floor = -h / 2
  const [kx, ky, kz] = look.mm ? [a / look.mm[0], b / look.mm[1], h / look.mm[2]] : [1, 1, 1]

  const root = new Group()
  const body = new Group()
  body.rotation.z = (quarter * Math.PI) / 2
  root.add(body)

  const lift = Math.min(look.lift ?? 0, Math.max(0, h - 4))
  const pcbT = look.pcb ? 1.6 : 0
  const top = floor + lift + pcbT
  if (look.pcb) {
    add(body, new BoxGeometry(a, b, pcbT), std(look.pcb), [0, 0, floor + lift + pcbT / 2])
    // posts under the corners
    if (lift > 0.5) {
      const post = std('#3a3a40')
      for (const [sx, sy] of [
        [1, 1],
        [-1, 1],
        [1, -1],
        [-1, -1],
      ])
        add(body, zcyl(1.6, lift, 16), post, [sx * (a / 2 - 2.5), sy * (b / 2 - 2.5), floor + lift / 2], false)
    }
  }

  // header strips and pins (canonical frame)
  const pins: { name: string; at: Vector3 }[] = []
  const stripMat = std('#18191b')
  const gold = std('#d9c37c', 0.7)
  const header = (names: string[], y: number, xs: number[]) => {
    if (!names.length) return
    const len = Math.max(...xs) - Math.min(...xs) + PITCH
    add(body, new BoxGeometry(len, PITCH, STRIP), stripMat, [
      (Math.max(...xs) + Math.min(...xs)) / 2,
      y,
      top + STRIP / 2,
    ])
    names.forEach((name, i) => {
      add(body, new BoxGeometry(0.64, 0.64, PIN_UP + 1), gold, [xs[i], y, top + STRIP + (PIN_UP - 1) / 2], false)
      pins.push({ name, at: new Vector3(xs[i], y, top + STRIP + PIN_UP) })
    })
  }
  if (partId === 'esp32_devkitc') {
    // the 48.26 mm PCB plus the antenna overhang at +x: rows centred on the PCB, not the box
    const xs = ESP32_ROWS[0].map((_, i) => 22.86 - PITCH * i - 3.02)
    header(ESP32_ROWS[0], b / 2 - 1.27, xs)
    header(ESP32_ROWS[1], -(b / 2 - 1.27), xs)
  } else if (isBoard) {
    const half = Math.ceil(pinNames.length / 2)
    const rows = [pinNames.slice(0, half), pinNames.slice(half)]
    const pitch = Math.min(PITCH, (a - 4) / Math.max(1, half))
    rows.forEach((row, r) =>
      header(
        row,
        (r ? -1 : 1) * (b / 2 - 1.27),
        row.map((_, i) => a / 2 - 2 - 2 - pitch * i),
      ),
    )
  } else if (pinNames.length) {
    const pitch = Math.min(PITCH, (a - 1) / pinNames.length)
    const x0 = (-(pinNames.length - 1) * pitch) / 2
    header(
      pinNames,
      b / 2 - 1.5,
      pinNames.map((_, i) => x0 + pitch * i),
    )
  }

  // shapes on top
  let screen: { ctx: CanvasRenderingContext2D; tex: CanvasTexture } | null = null
  const leds: MeshStandardMaterial[] = []
  const paint = (s: { color: string; metal?: number; glow?: true }) => {
    const m = std(s.color, s.metal)
    if (s.glow) {
      m.emissive.set(s.color)
      m.emissiveIntensity = 0
      leds.push(m)
    }
    return m
  }
  for (const s of look.shapes) {
    if ('box' in s) {
      const [sx, sy, sz] = [Math.min(s.box[0] * kx, a - 0.5), Math.min(s.box[1] * ky, b - 0.5), s.box[2] * kz]
      add(body, new BoxGeometry(sx, sy, sz), std(s.color, s.metal), [
        s.at[0] * a,
        s.at[1] * b,
        top + (s.on ?? 0) * kz + sz / 2,
      ])
    } else if ('cyl' in s && s.axis) {
      const x = s.axis === 'x'
      const r = Math.min(s.cyl[0] * Math.min(x ? ky : kx, kz), (x ? b : a) / 2 - 0.3, h / 2)
      const len = Math.min(s.cyl[1] * (x ? kx : ky), x ? a : b)
      const geo = new CylinderGeometry(r, r, len, 28)
      if (x) geo.rotateZ(Math.PI / 2)
      add(body, geo, paint(s), [s.at[0] * a, s.at[1] * b, top + (s.on ?? 0) * kz + r], false)
    } else if ('cyl' in s) {
      const r = Math.min(s.cyl[0] * Math.min(kx, ky), a / 2 - 0.3, b / 2 - 0.3)
      const ch = s.cyl[1] * kz
      add(body, zcyl(r, ch), paint(s), [s.at[0] * a, s.at[1] * b, top + (s.on ?? 0) * kz + ch / 2], false)
    } else if ('led' in s) {
      const m = std(s.color)
      m.emissive.set(s.color)
      m.emissiveIntensity = 0
      leds.push(m)
      add(body, new BoxGeometry(...s.led), m, [s.at[0] * a, s.at[1] * b, top + s.led[2] / 2], false)
    } else if ('dome' in s) {
      const r = Math.min(s.dome * Math.min(kx, ky), a / 2, b / 2)
      const geo = new SphereGeometry(r, 32, 16, 0, Math.PI * 2, 0, Math.PI / 2).rotateX(Math.PI / 2)
      add(body, geo, paint(s), [s.at[0] * a, s.at[1] * b, top + (s.on ?? 3) * kz], false)
    } else if ('screen' in s) {
      const canvas = document.createElement('canvas')
      canvas.width = 256
      canvas.height = 128
      const ctx = canvas.getContext('2d')
      if (ctx) {
        const tex = new CanvasTexture(canvas)
        tex.colorSpace = SRGBColorSpace
        screen = { ctx, tex }
        drawScreen(ctx, 'off', 0)
        const [sx, sy] = [Math.min(s.screen[0], a - 2), Math.min(s.screen[1], b - 2)]
        const m = add(
          body,
          new PlaneGeometry(sx, sy),
          new MeshBasicMaterial({ map: tex }),
          [s.at[0] * a, s.at[1] * b, top + 1.45],
          false,
        )
        m.renderOrder = 1
      }
    } else if ('ring' in s) {
      const [ro, ri] = [Math.min(s.ring[0], a / 2, b / 2), s.ring[1]]
      add(body, zcyl(ro, 1.6, 48), std('#18191b'), [0, 0, floor + 0.8], false)
      add(body, zcyl(ri, 1.7, 48), std('#202024'), [0, 0, floor + 0.8], false)
      for (let i = 0; i < s.leds; i++) {
        const t = (i / s.leds) * Math.PI * 2
        const color = `hsl(${Math.round((i / s.leds) * 360)}, 90%, 60%)`
        const m = std('#f2f2f2')
        m.emissive.set(color)
        m.emissiveIntensity = 0
        leds.push(m)
        add(
          body,
          new BoxGeometry(5, 5, 1.6),
          m,
          [(Math.cos(t) * (ro + ri)) / 2, (Math.sin(t) * (ro + ri)) / 2, floor + 2.4],
          false,
        )
      }
    }
  }

  // canonical -> root coordinates
  const toRoot = (v: Vector3) => v.clone().applyAxisAngle(new Vector3(0, 0, 1), body.rotation.z)
  const usb = isBoard
    ? {
        at: toRoot(new Vector3(-a / 2, 0, top + 1.5)),
        dir: toRoot(new Vector3(-1, 0, 0)),
      }
    : null

  let power = ''
  return {
    root,
    pins: pins.map((p) => ({ name: p.name, at: toRoot(p.at) })),
    usb,
    mats,
    setPower(state, progress = 0) {
      const key = state === 'upload' ? `u${Math.round(progress * 40)}` : state
      if (key === power) return
      power = key
      if (screen) {
        drawScreen(screen.ctx, state, progress)
        screen.tex.needsUpdate = true
      }
      // a board's LED blinks while it uploads; lights stay lit once the code runs
      const blink = state === 'upload' ? Math.round(progress * 40) % 2 : 0
      leds.forEach((m) => {
        m.emissiveIntensity = isBoard
          ? state === 'upload'
            ? blink * 2.5
            : state === 'on'
              ? 1.2
              : 0
          : state === 'on'
            ? 1.6
            : 0
      })
    },
  }
}
