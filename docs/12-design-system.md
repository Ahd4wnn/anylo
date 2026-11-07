# 12 · Design system

> **Bill anything. Sell anything. Run everything.**

**Look and feel:** calm, precise, trustworthy, like a good bank app crossed with a fast POS. Clean surfaces, one confident accent colour, strong typography, and numbers that line up. **No** gradients, glows, glassmorphism, emoji in UI copy or stock icons as the logo.

## 1. Brand

| Item | Spec |
|---|---|
| Name | **Anylo** (always capital A, rest lowercase) |
| Motto | *Bill anything. Sell anything. Run everything.* Used on the landing hero, login, splash and the receipt footer option |
| Logo | Wordmark "anylo" in a geometric sans, lowercase. The symbol is a rounded square containing an abstract **"A" formed by a rising bar-chart stroke** (sales going up). One colour. Works at 16 px. Deliverables: SVG mark, wordmark, lockup, app icons (Android adaptive + monochrome, iOS), favicon, PWA maskable |
| Voice | Plain, warm, direct. "Bill saved" not "Transaction completed successfully". Say "you", avoid jargon, and explain GST terms inline the first time they appear |

## 2. Colour tokens

Tokens are defined once in `design/tokens.json`. That file generates Tailwind config (web), `Color.kt` (Android) and the asset catalog (iOS). **Raw hex values in components are a lint error.**

### Brand ramp: "Anylo Indigo"
| step | hex |
|---|---|
| 50 | `#EEF0FF` |
| 100 | `#DDE1FF` |
| 200 | `#BCC3FF` |
| 300 | `#959FFB` |
| 400 | `#6E78F2` |
| **500** | **`#4F55E3`** (primary) |
| 600 | `#3E41C8` |
| 700 | `#3133A0` |
| 800 | `#272A7D` |
| 900 | `#1E2060` |

### Semantic (light / dark)
| token | light | dark | use |
|---|---|---|---|
| `bg` | `#F7F7F5` | `#0E0F12` | app canvas |
| `surface` | `#FFFFFF` | `#16171C` | cards, sheets |
| `surface-2` | `#F1F1EE` | `#1E2027` | inputs, table stripes |
| `border` | `#E3E3DE` | `#2A2C35` | hairlines |
| `border-strong` | `#CFCFC8` | `#3A3D48` | inputs |
| `text` | `#15161A` | `#F2F2F4` | primary text |
| `text-2` | `#53555E` | `#A7A9B3` | secondary |
| `text-3` | `#80838C` | `#757884` | tertiary, placeholders (never for essential info) |
| `primary` | brand-500 | brand-400 | actions, focus |
| `primary-fg` | `#FFFFFF` | `#0E0F12` | text on primary |
| `success` | `#16834F` | `#3CC489` | paid, achieved |
| `warning` | `#B26A00` | `#F0A93B` | due, at risk |
| `danger` | `#C42B2B` | `#F06A6A` | errors, delete, behind |
| `info` | `#2563A8` | `#6FA8EC` | neutral notices |

### Domain colours (charts and badges only)
| token | hex | use |
|---|---|---|
| `pay-cash` | `#16834F` | cash |
| `pay-upi` | `#4F55E3` | UPI |
| `pay-card` | `#7A4FD6` | card |
| `pay-due` | `#B26A00` | due / credit |

The chart palette (categorical, colour-blind safe, max 8): brand-500, `#0F9D9A`, `#E07B39`, `#7A4FD6`, `#D64F7A`, `#5E8C31`, `#B8932E`, `#64748B`. Every pair is checked with the dataviz validator. Text contrast ≥ 4.5:1 is verified in both themes.

## 3. Typography

- **UI font:** Inter (variable, 400–700). Indic text falls back to Noto Sans Devanagari, Malayalam, Tamil and Kannada, which are bundled on Android and web so receipts and screens render identically.
- **Numbers:** `font-variant-numeric: tabular-nums` everywhere money appears. The ₹ sign sits next to the number with a thin space.

| token | size / line height | weight | use |
|---|---|---|---|
| display | 32/40 | 700 | dashboard hero number |
| h1 | 24/32 | 650 | page titles |
| h2 | 20/28 | 600 | section titles |
| h3 | 17/24 | 600 | card titles |
| body | 16/24 | 450 | default (mobile body 16, never smaller for primary content) |
| body-sm | 14/20 | 450 | table cells, secondary |
| caption | 12/16 | 500 | labels, badges (uppercase only for ≤ 2 words) |
| money-lg | 28/34 | 650 tnum | POS total |

On Android, `sp` units follow the user's font scale. PlantBill's fixed-scale override is not used; layouts are tested at 1.3×.

## 4. Space, shape, elevation

- Spacing scale (4-pt): 0, 2, 4, 8, 12, 16, 20, 24, 32, 40, 48, 64.
- Radius:
  - `sm` 6: chips, badges
  - `md` 10: inputs, buttons
  - `lg` 14: cards
  - `xl` 20: sheets, dialogs
  - `full`: avatars, pills
- Elevation:
  - `e0` border only (default for cards)
  - `e1` `0 1px 2px rgb(0 0 0 / .06)` (sticky bars)
  - `e2` `0 8px 24px rgb(0 0 0 / .12)` (menus, dialogs)

  Use **either a border or a shadow on an element, never both.** Dark mode uses borders plus surface steps instead of shadows.
- Touch targets ≥ 48 dp. The primary POS action (Pay, Save) is 56 dp tall and full width on mobile.

## 5. Motion

- Durations: 120 ms (press, hover), 200 ms (sheets, dialogs), 300 ms (page transitions). Easing `cubic-bezier(.2,.8,.2,1)`.
- Only `transform` and `opacity` are animated. No `transition: all`.
- `prefers-reduced-motion` and the Android "remove animations" setting reduce motion to fades only.
- The success check after saving a bill is the one celebratory animation (≤ 600 ms).

## 6. Components (web: Radix primitives + Tailwind, shadcn-style, in `web/src/ui/`)

| Component | Notes |
|---|---|
| Button | `primary`, `secondary`, `ghost`, `danger`, `link`; sizes sm/md/lg/xl (POS); loading state keeps the width |
| IconButton | Always has an `aria-label` |
| Input, MoneyInput, QtyInput, PhoneInput, GstinInput | MoneyInput formats in en-IN on blur and parses paise exactly; GstinInput validates and checksums live |
| Select, Combobox (search), DatePicker, DateRangePicker (presets) | |
| Dialog, Sheet (bottom on mobile, side on desktop), AlertDialog (destructive confirm), TypeToConfirm | **No native `alert` / `confirm`** |
| Toast | Undo action for soft deletes (5 s) |
| Card, StatTile (value, delta, sparkline), ProgressGoal | |
| DataTable | TanStack Table: sort, column visibility, sticky header, virtualised rows, CSV export; dense and comfortable modes |
| Tabs, SegmentedControl, Badge, Tag, Avatar, EmptyState, ErrorState, Skeleton | |
| Charts | Recharts wrappers `TrendChart`, `BarList`, `Donut`, `HeatStrip` using the tokens |
| Keypad | Large numeric keypad for touch POS |
| ReceiptPreview | Canvas renderer shared with printing |

Android has matching Compose components in `ui/components/` with the same names. iOS has SwiftUI equivalents.

## 7. Layout patterns

| Surface | Desktop (≥ 1024) | Tablet | Phone |
|---|---|---|---|
| POS | Three panes: catalogue (search + grid/list) · cart table · payment summary. Keyboard first | Two panes: catalogue · cart+pay | Catalogue full screen + bottom cart bar → checkout sheet |
| Back office `/app` | Left sidebar (collapsible), top bar with shop switcher, search (⌘K), notifications, AI button | Collapsed rail | Bottom nav (5): Home · Sell · Items · Reports · More |
| Admin | Sidebar + data tables | Same | Usable but not optimised |

**Settings** are split into sections, never one long page:
- Business
- Tax & invoices
- Printing
- Payments (UPI)
- Staff
- Notifications & WhatsApp
- Subscription
- Data & export

## 8. Content rules

- Money: `₹1,25,450.75`. Show paise only when non-zero in lists; always show them on invoices.
- Dates: `8 Nov 2026`, time `2:32 pm`. Relative ("2 h ago") only in feeds.
- Empty states: one sentence on what goes here, plus one primary action.
- Errors: what happened + what to do. Never show raw codes to users (they are logged).
- i18n: every string goes through `t()` (web: react-i18next, Android: resources, iOS: String Catalog). Languages: en, hi, ml, ta, kn. Translations are reviewed by native speakers before release; PlantBill's machine drafts are only a starting point.

## 9. Accessibility (WCAG 2.1 AA)

- Contrast is checked in CI (token pairs).
- Visible focus ring: 2 px `primary` + 2 px offset.
- Full keyboard operation of the POS and back office.
- Screen-reader labels on icon buttons, charts (summary text) and money (reads "rupees").
- Colour is never the only signal: status badges include text or icons.
