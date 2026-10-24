---
name: Finanse
description: One-owner personal-finance dashboard; neutral page, ink figures, colour only where it names a holding or category.
colors:
  ground: "#f8f7f4"
  ink: "#18181b"
  ink-2: "#4a4a52"
  ink-3: "#66666e"
  rule: "#e2e0db"
  rule-strong: "#b3b1ab"
  bar: "#3f3f46"
  tint: "rgba(24, 24, 27, 0.05)"
  focus: "#2a78d6"
  select: "#d6e4f7"
  h-stocks: "#2a78d6"
  h-bonds: "#eb6834"
  c-green: "#1baf7a"
  c-amber: "#eda100"
  s5: "#e87ba4"
  s6: "#008300"
  s7: "#6250d6"
  s8: "#e34948"
  ground-dark: "#131314"
  ink-dark: "#ececee"
  ink-3-dark: "#8f8f97"
  rule-dark: "#2a2a2e"
  bar-dark: "#a8a8b0"
typography:
  figure:
    fontFamily: "Public Sans, system-ui, sans-serif"
    fontSize: "2.25rem"
    fontWeight: 700
    lineHeight: 1.1
    letterSpacing: "-0.02em"
    fontFeature: "\"tnum\" 1"
  body:
    fontFamily: "Public Sans, system-ui, sans-serif"
    fontSize: "0.9375rem"
    fontWeight: 400
    lineHeight: 1.45
    fontFeature: "\"tnum\" 1"
  label:
    fontFamily: "Public Sans, system-ui, sans-serif"
    fontSize: "0.9375rem"
    fontWeight: 600
    lineHeight: 1.45
rounded:
  mark: "2px"
  bar: "3px"
  segment: "6px"
  control: "8px"
spacing:
  gutter: "16px"
  gutter-desktop: "32px"
  section: "24px"
  column-gap: "56px"
components:
  segmented:
    backgroundColor: "{colors.tint}"
    rounded: "{rounded.control}"
    padding: "2px"
  segmented-option:
    textColor: "{colors.ink-3}"
    typography: "{typography.label}"
    rounded: "{rounded.segment}"
    padding: "5px 10px"
    height: "32px"
  segmented-option-selected:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.ground}"
  icon-button:
    backgroundColor: "{colors.tint}"
    rounded: "{rounded.control}"
    size: "36px"
  text-button:
    textColor: "{colors.ink}"
    padding: "8px 0"
    height: "40px"
---

# Design System: Finanse

## Overview

**Creative North Star: "The Ledger Page"**

A single neutral page of figures, ruled rather than boxed. The page opens straight on Net worth: no header band, no title bar, no cards. Numbers are ink and carry their polarity in the sign; the only hues on the page name a thing (a holding or a spending category), never a judgement. Data freshness is pushed to the footer, where stale sources announce themselves by line form.

Density is moderate and list-like: two-line rows, hairline rules between entries, one large figure per section at most. Desktop is two columns; a phone reads one column in a fixed order.

**Key Characteristics:**
- Neutral warm-paper ground (light) and near-black (dark); both themes are full token scopes.
- Two type sizes; hierarchy by weight and ink level.
- Tabular numerals everywhere.
- Colour is categorical and fixed per thing; polarity is "+" / "−".
- Hairline rules, no shadows, no containers.

## Colors

A neutral ink-on-paper base with an eight-slot categorical palette that appears only as small marks and bars.

### Primary
- **Stocks Blue** (h-stocks): holding slot 1; also the stocks profit line above zero, and the focus ring hue.

### Secondary
- **Bonds Orange** (h-bonds), **Green** (c-green, categorical slot 3), **Amber** (c-amber): categorical slots 2–4 (3 and 4 are spending colours only).
- **Slots 5–8** (s5 pink, s6 green, s7 violet, s8 red): extra categorical hues for spending categories only, in a fixed categorical order. Slots 1–4 alias h-stocks, h-bonds, c-green and c-amber.

### Neutral
- **Paper** (ground / ground-dark): page background; also selected-segment text.
- **Ink** (ink): figures, names, amounts; the selected-segment fill.
- **Ink 2** (ink-2): secondary text (profit lines, side values, freshness emphasis).
- **Ink 3** (ink-3): labels, meta lines, currency suffixes, chart axis text, the stocks line below zero.
- **Rule** (rule): every hairline divider. **Rule Strong** (rule-strong) is defined for heavier dividers.
- **Bar** (bar): neutral fill for minor spending categories. **Tick** equals ink: the previous-period marker.
- **Tint** (tint): quiet fill behind controls and skeletons. **Select** (select): text selection.

### Named Rules
**The Sign Not Colour Rule.** Gains and losses are told by "+" / "−" / "±" and ink, never red/green. The stocks chart fills above zero in the stocks hue and below zero in ink-3.

**The Fixed Slot Rule.** A category's colour follows the category, never its rank: rent 7, groceries 3, eat-out 2, leisure 5, transportation 1, subscriptions 4, shopping 8, travel 6. Anything unmapped is neutral bar.

**The Named Things Rule.** Hue appears only as swatches, allocation segments, category bars, category dots and the stocks line. Text is always neutral ink.

## Typography

**Body Font:** Public Sans (self-hosted variable, with system-ui, sans-serif)

**Character:** One sober grotesque at two sizes; tabular numerals make columns of money line up without a table.

### Hierarchy
- **Figure** (700, 2.25rem, 1.1, -0.02em): the headline amount of a section (net worth, month spent). Currency suffix at 500 in ink-3.
- **Body** (400, 0.9375rem, 1.45): everything else.
- **Label** (600, 0.9375rem, ink-3): section headings, sentence case.
- Within body size, weight ranks: 700 amounts and holding names, 600 row names, 500 sub-rows.

### Named Rules
**The Two Sizes Rule.** Only `--fs` and `--fl` exist. Rank by weight and ink level, not size. Known exception: the chart's axis text is library chrome at 12px.

## Layout

Single column under 960px with `order` fixing the reading path: net worth, stocks, spending, recent, uncategorised, footer. At 960px and up, two columns (5fr / 7fr, 56px gap, max-width 1200px): net worth and recent transactions left; stocks, spending and uncategorised right; footer spans both. Gutter 16px, 32px on desktop. Sections are separated by a hairline top rule and 24px vertical padding; the first section in each column has no rule.

## Elevation & Depth

Flat. No shadows anywhere; separation is hairline rules and the faint tint fill behind controls.

## Shapes

Small, quiet corners: 2px on swatches and allocation segments, 3px on the end of category bars, 6px inside segmented options, 8px on controls. Category dots are circles. Disclosure chevrons are drawn as two-sided bordered squares rotated 45°, not glyphs.

## Components

### Row
Two-line grid: name / amount on the first line (600 / 700, amount right-aligned), meta / side value on the second (ink-3 / ink-2). Text truncates with ellipsis; amounts never wrap.

### Earned Strip
Four cells (Day, Week, Month, Year) between top and bottom rules, separated by vertical hairlines; label in ink-3, signed amount at 700. Under 460px it becomes 2×2.

### Allocation Bar
10px tall, holding-coloured segments sized by value, 2px gaps, minimum 4px each. The holding rows below act as its legend (10px swatch).

### Holding Rows
Expandable rows (swatch, two-line row, chevron). Stocks expand into one group per account, bonds into one group per series; each group head shows its % share of the holding in ink-3.

### Segmented Control
Tint track, 8px radius; options 600 ink-3, min 44×32px. Selected = ink fill with ground text. Arrow keys move the selection.

### Spending
Month navigator (two 36px tint icon buttons with stroked SVG chevrons), the month total as a figure, then "Income … · saved N%" in ink-2. Category rows: name, 8px bar in the category's slot colour, amount; a 2px ink tick marks the previous period's amount. Rows expand to their transactions.

### Transaction List
Rows split by hairlines; the meta line opens with an 8px category dot in the category's colour.

### Footer Freshness
Ink-3 source timestamps; a stale source turns ink-2, 600, with a 1.5px dashed underline.

## Do's and Don'ts

### Do:
- **Do** open on the Net worth figure; keep freshness in the footer.
- **Do** write polarity as "+" / "−" and keep figures in ink.
- **Do** colour a category from its fixed slot; leave minor ones on neutral bar.
- **Do** separate with hairline rules and whitespace.

### Don't:
- **Don't** add a third type size outside chart chrome.
- **Don't** colour text or numbers red/green for gains and losses.
- **Don't** assign category colours by rank or order.
- **Don't** wrap sections in cards, boxes or shadows, or add a header band.
