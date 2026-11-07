# 12 · Design system

> **Bill anything. Sell anything. Run everything.**

**Look and feel:** confident, premium and unmistakable. Deep navy foundations, a royal-blue core, and a single flash of **Energy Orange** where money happens. The look should stick in memory: shops should recognise Anylo across the room. Clean surfaces, strong typography, numbers that line up. **No** gradients, glows, glassmorphism, emoji in UI copy, or stock icons as the logo.

## 1. Brand

| Item | Spec |
|---|---|
| Name | **Anylo** (always capital A, rest lowercase) |
| Motto | *Bill anything. Sell anything. Run everything.* Used on the landing hero, login, splash and the receipt footer option |
| Logo | **Official mark: `design/brand/anylo-mark.png`** (2000×2000): a soft, rounded white **"A"** (a hollow left stroke and a solid right stroke joined by a curved base) on **Bright Indigo** (`#4F6BFF`; the source file samples `#5170FF` and is normalised to `#4F6BFF`). The mark is the app icon, favicon, splash and avatar. The wordmark "anylo" (lowercase, geometric sans, Deep Blue on light / white on dark) sits to the right of the mark in the horizontal lockup. **To do (M0):** trace the PNG to `anylo-mark.svg` (single path), then export Android adaptive icon (white A foreground, indigo background, plus monochrome layer), iOS app icon, PWA icons 192/512/maskable and favicon 32/16. On Deep Blue backgrounds the mark keeps its indigo tile; it is never recoloured orange |
| Signature moment | The **orange Pay / Save bill button** and the orange success tick. Orange appears almost nowhere else, so it always means "money is happening" |
| Voice | Plain, warm, direct. "Bill saved", not "Transaction completed successfully". Say "you", avoid jargon, and explain GST terms inline the first time they appear |

## 2. Colour

Tokens are defined once in `design/tokens.json`, which generates the Tailwind config (web), `Color.kt` (Android) and the asset catalog (iOS). **Raw hex values in components are a lint error.**

### 2.1 Brand palette (the six source colours)

| Name | Hex | Role | Rules (contrast measured) |
|---|---|---|---|
| **Deep Blue** | `#031273` | Brand anchor: sidebar, POS total panel, landing hero, headings on light, logo wordmark | White on it 15.7:1 |
| **Royal Blue** | `#0504AA` | **Primary** in light mode: buttons, links, active nav, focus, selected states | White on it 13.1:1 |
| **Bright Indigo** | `#4F6BFF` | **Logo colour** and app-icon tile; primary family for dark mode, charts, illustrations, info badges | 4.3:1 on white, so never for small text on white; 4.5:1 on the dark bg |
| **Energy Orange** | `#FF4800` | **Accent, used sparingly**: Pay / Save bill / Subscribe CTAs, success tick, the logo bar, "new" dots, the active goal ring | White text only at ≥ 18 px bold (3.4:1 = AA large); Deep Blue text 4.6:1 for small labels |
| **Orange-Yellow** | `#F59E0B` | Highlight & caution: dues, "at risk" goals, low stock, trial banner | Never as text on white (2.2:1); Deep Blue text on it 7.3:1 |
| **Sea White** | `#D7F2FA` | Cool tint: selected rows, info panels, empty-state backgrounds, hero sections, chips | Deep Blue on it 13.4:1; Royal on it 11.2:1 |

**Why all six work together:** the blues do the structural work (60%), white, Sea White and neutrals carry content (35%), and the two oranges are rare signals (≤ 5%). Orange-Yellow never sits next to Energy Orange as a pair of fills. They have different jobs (caution vs action), so the screen never turns into a sunset.

### 2.2 Ramps (generated, used for hovers/tints)

| step | blue (Royal → Deep) | indigo | orange (Energy) | amber (Orange-Yellow) | sea |
|---|---|---|---|---|---|
| 50 | `#EEF0FF` | `#EEF1FF` | `#FFF1EB` | `#FFF8E6` | `#F2FBFD` |
| 100 | `#DCE0FF` | `#DDE3FF` | `#FFDCCC` | `#FDECC2` | `#E6F7FC` |
| 200 | `#B5BCF7` | `#BCC7FF` | `#FFB899` | `#FBD786` | `#D7F2FA` ★ |
| 300 | `#7F86E6` | `#8FA0FF` | `#FF8F5C` | `#F8BD45` | `#B5E5F3` |
| 400 | `#4048CC` | `#6F86FF` | `#FF6A2E` | `#F59E0B` ★ | `#86D2E8` |
| 500 | `#0504AA` ★ | `#4F6BFF` ★ | `#FF4800` ★ | `#D98706` | `#55B8D6` |
| 600 | `#05048F` | `#3D55E0` | `#DB3D00` | `#B45309` | `#2F98B8` |
| 700 | `#041080` | `#3043B3` | `#B03100` | `#8C4207` | `#217793` |
| 800 | `#031273` ★ | `#243386` | `#852500` | `#663005` | `#185A70` |
| 900 | `#020A45` | `#18225A` | `#5C1A00` | `#402003` | `#0F3B4A` |

★ = a source colour. Ramps are a starting point; final values are validated by the token contrast test in CI.

### 2.3 Semantic tokens (light / dark)

| token | light | dark | use |
|---|---|---|---|
| `bg` | `#F5F7FC` | `#050A2E` | app canvas (dark is a Deep-Blue night, never grey) |
| `surface` | `#FFFFFF` | `#0B1340` | cards, sheets |
| `surface-2` | `#EEF2FA` | `#111B52` | inputs, table stripes |
| `tint` | `#D7F2FA` (Sea White) | `#13235E` | selected rows, info panels |
| `border` | `#DFE4F0` | `#1F2A66` | hairlines |
| `border-strong` | `#C3CBDD` | `#2E3B80` | inputs |
| `text` | `#0B1033` | `#EEF3FF` | primary text (17:1) |
| `text-2` | `#4A5275` | `#A9B4DD` | secondary (≥ 7.6:1 / 8.7:1) |
| `text-3` | `#7A82A3` | `#7381B5` | placeholders and hints only, never essential info |
| `primary` | `#0504AA` Royal | `#7B90FF` | main actions, links, focus ring |
| `primary-hover` | `#031273` Deep | `#8FA0FF` | |
| `on-primary` | `#FFFFFF` | `#031273` | text on primary (13.1:1 / 5.4:1) |
| `accent` | `#FF4800` Energy | `#FF6A2E` | Pay / Save / Subscribe, success tick |
| `on-accent` | `#FFFFFF` (≥ 18 px bold) | `#FFFFFF` (≥ 18 px bold) | accent buttons are always large |
| `highlight` | `#F59E0B` | `#F59E0B` | dues, at-risk, trial banner fill (text on it: `#031273`) |
| `success` | `#0B7A54` | `#34D399` | paid, achieved, in stock |
| `danger` | `#C8102E` | `#FF6B7D` | errors, delete, behind target (crimson, kept distinct from Energy Orange and always paired with an icon or text) |
| `info` | `#4F6BFF` (icons/fills only) | `#8FA0FF` | neutral notices |

### 2.4 Domain colours (charts and badges only)

| token | light | dark | use |
|---|---|---|---|
| `pay-cash` | `#0B7A54` | `#34D399` | cash |
| `pay-upi` | `#0504AA` | `#8FA0FF` | UPI |
| `pay-card` | `#4F6BFF` | `#BCC7FF` | card |
| `pay-due` | `#F59E0B` | `#F59E0B` | due / credit |

Chart palette (categorical, max 6, ordered): `#0504AA`, `#FF4800`, `#4F6BFF`, `#F59E0B`, `#55B8D6` (sea-500), `#031273`. Series 7+ fold into "Others" (`#C3CBDD`). Each adjacent pair is checked with the dataviz validator. Lines are 2 px with direct labels, so colour is never the only key.

### 2.5 Signature compositions

- **POS:** white catalogue, Sea-White selected tiles, and a **Deep Blue checkout panel** with a big white total and an **Energy Orange "Pay ₹1,240" button**. This is the most-seen screen and the one people remember.
- **Dashboard hero:** a Deep Blue card with white KPI numbers, a Bright Indigo sparkline, and an Energy Orange goal ring.
- **Landing / splash:** a Deep Blue field, the motto in white with "everything." in Energy Orange, and Sea-White product cards.
- **Receipt (thermal):** monochrome by necessity; the brand appears only in the logo and the footer motto.

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
