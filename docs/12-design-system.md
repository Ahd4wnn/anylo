# 12 · Design system

> **Bill anything. Sell anything. Run everything.**

**Look and feel: "Mist".** Light, calm and airy, like a modern fintech app. Cool near-white canvases, soft indigo from the logo family, soft ink text (never pure black), gentle status colours, and generous white space. Nothing shouts: the **content and numbers** are the loudest thing on screen. **No** gradients, glows, glassmorphism, neon or saturated orange, and no emoji in UI copy.

## 1. Brand

| Item | Spec |
|---|---|
| Name | **Anylo** (always capital A, rest lowercase) |
| Motto | *Bill anything. Sell anything. Run everything.* Used on the landing hero, login, splash and the receipt footer option |
| Logo | **Official mark: `design/brand/anylo-mark.png`** (2000×2000): a soft, rounded white **"A"** (a hollow left stroke and a solid right stroke joined by a curved base) on **Bright Indigo** (`#4F6BFF`; the source file samples `#5170FF` and is normalised to `#4F6BFF`). The mark is the app icon, favicon, splash and avatar. The wordmark "anylo" (lowercase, geometric sans, `text` colour) sits to the right of the mark in the horizontal lockup. **To do (M0):** trace the PNG to `anylo-mark.svg` (single path), then export Android adaptive icon (white A foreground, indigo background, plus monochrome layer), iOS app icon, PWA icons 192/512/maskable and favicon 32/16. The tile colour is always `logo` (`#4F6BFF`) in both themes |
| Voice | Plain, warm, direct. "Bill saved", not "Transaction completed successfully". Say "you", avoid jargon, and explain GST terms inline the first time they appear |

## 2. Colour: the "Mist" theme

Tokens are defined once in `design/tokens.json`, which generates `web/src/styles/tokens.css` (and later `Color.kt` and the iOS asset catalog). **Raw hex values in components are a lint error.** Contrast is measured; text pairs meet WCAG AA.

> History: a saturated navy / royal / orange palette was tried on 2026-11-08 and rejected as feeling like a stationery brand. Mist replaced it the same day.

### 2.1 Semantic tokens (light / dark)

| token | light | dark | use |
|---|---|---|---|
| `bg` | `#F7F8FC` | `#12141C` | app canvas |
| `surface` | `#FFFFFF` | `#1A1D28` | cards, sheets, inputs |
| `surface-2` | `#F2F4F9` | `#222634` | table stripes, hovers |
| `tint` | `#EEF1FB` | `#232846` | brand panels, selected rows |
| `border` / `border-strong` | `#E4E7F0` / `#CDD2E0` | `#2A2F3E` / `#3A4052` | hairlines / inputs |
| `text` | `#1F2433` | `#E8EAF2` | primary text (14.6:1 / 15.3:1) |
| `text-2` | `#5D6478` | `#A3A9BC` | secondary (5.9:1 / 7.2:1) |
| `text-3` | `#8A90A3` | `#7A8196` | placeholders and hints only |
| `primary` | `#4A5AE0` | `#8C96FF` | buttons, links, focus (white on it 5.5:1) |
| `primary-hover` | `#3D4CCB` | `#A3ABFF` | |
| `on-primary` | `#FFFFFF` | `#12141C` | |
| `primary-soft` / `on-primary-soft` | `#EEF0FE` / `#3D4CCB` | `#262B4D` / `#C5CBFF` | secondary buttons, chips, selected nav |
| `brand` | `#5B6CF0` | `#8C96FF` | icons, large display words, chart series 1 |
| `logo` | `#4F6BFF` | `#4F6BFF` | the logo tile only |
| `success` / `-soft` | `#2F8466` / `#E6F4EE` | `#5CC59E` / `#18302A` | paid, achieved |
| `warning` / `-soft` / `-fill` | `#9A6B12` / `#FBF3E2` / `#D9A441` | `#E6BC6A` / `#33291A` / `#D9A441` | dues, at risk, trial banner |
| `danger` / `-soft` | `#C0444A` / `#FBECEC` | `#EE7E83` / `#3A2024` | errors, delete, behind |

Soft fills (`*-soft`) carry status; saturated colour is used only for text and small marks. **The Pay / Save bill button is the normal primary button, only larger** (56 px, full width). Prominence comes from size and position, not a loud colour.

### 2.2 Data colours (charts and badges)

| token | light | dark |
|---|---|---|
| `pay-cash` | `#3E9C7A` | `#5CC59E` |
| `pay-upi` | `#5B6CF0` | `#8C96FF` |
| `pay-card` | `#8C96FF` | `#C5CBFF` |
| `pay-due` | `#D9A441` | `#E6BC6A` |

Chart palette (ordered, max 6): `#5B6CF0`, `#3E9C7A`, `#D9A441`, `#8C96FF`, `#6FB7C9`, `#B07CC6`. Further series fold into "Others" (`#CDD2E0`). Lines are 2 px with direct labels, so colour is never the only key.

### 2.3 Signature compositions

- **POS:** white catalogue on the `bg` canvas, `tint` for selected tiles, a white checkout card with a large `text` total and a full-width primary **Pay ₹1,240** button.
- **Dashboard:** white cards on `bg`; the hero KPI card on `tint` with a `brand` sparkline.
- **Login / landing:** a rounded `tint` panel holding the motto in `text`, with "everything." in `brand`; the form on the plain canvas.
- **Receipt (thermal):** monochrome; brand appears only in the logo and the footer motto.

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
