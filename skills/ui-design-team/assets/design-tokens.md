# Design Token Definitions

Standard design tokens for cross-platform consistency. Use as a starting point for new projects.

## Color Palette

### Primary (Blue)
| Token | Hex | Usage |
|-------|-----|-------|
| primary-50 | #EFF6FF | Subtle backgrounds |
| primary-100 | #DBEAFE | Light backgrounds |
| primary-200 | #BFDBFE | Borders, dividers |
| primary-300 | #93C5FD | Disabled states |
| primary-400 | #60A5FA | Icons, secondary |
| primary-500 | #3B82F6 | **Primary brand color** |
| primary-600 | #2563EB | Hover states |
| primary-700 | #1D4ED8 | Active/pressed |
| primary-800 | #1E40AF | Dark accents |
| primary-900 | #1E3A8A | Darkest accents |

### Neutral (Gray)
| Token | Hex | Usage |
|-------|-----|-------|
| neutral-50 | #F9FAFB | Page background |
| neutral-100 | #F3F4F6 | Card backgrounds |
| neutral-200 | #E5E7EB | Borders |
| neutral-300 | #D1D5DB | Disabled text |
| neutral-400 | #9CA3AF | Placeholder text |
| neutral-500 | #6B7280 | Secondary text |
| neutral-600 | #4B5563 | Body text |
| neutral-700 | #374151 | Headings |
| neutral-800 | #1F2937 | Dark surfaces |
| neutral-900 | #111827 | Primary text |

### Semantic Colors
| Token | Hex | Usage |
|-------|-----|-------|
| success-500 | #22C55E | Success states, confirmations |
| warning-500 | #F59E0B | Warnings, caution |
| error-500 | #EF4444 | Errors, destructive actions |
| info-500 | #3B82F6 | Information, links |

## Spacing Scale

Based on 8px grid system:

| Token | px | rem | Usage |
|-------|-----|-----|-------|
| spacing-0 | 0 | 0 | Reset |
| spacing-px | 1 | 0.0625 | Hairline borders |
| spacing-0.5 | 2 | 0.125 | Micro spacing |
| spacing-1 | 4 | 0.25 | Tight spacing |
| spacing-2 | 8 | 0.5 | Compact spacing |
| spacing-3 | 12 | 0.75 | Default gap |
| spacing-4 | 16 | 1 | **Standard spacing** |
| spacing-5 | 20 | 1.25 | Medium spacing |
| spacing-6 | 24 | 1.5 | Section spacing |
| spacing-8 | 32 | 2 | Large spacing |
| spacing-10 | 40 | 2.5 | Extra spacing |
| spacing-12 | 48 | 3 | Section margins |
| spacing-16 | 64 | 4 | Page margins |

## Typography Scale

| Token | px | rem | Line Height | Usage |
|-------|-----|-----|-------------|-------|
| text-xs | 12 | 0.75 | 1.5 | Captions, labels |
| text-sm | 14 | 0.875 | 1.5 | Secondary text |
| text-base | 16 | 1 | 1.5 | **Body text** |
| text-lg | 18 | 1.125 | 1.5 | Large body |
| text-xl | 20 | 1.25 | 1.4 | H6 |
| text-2xl | 24 | 1.5 | 1.4 | H5 |
| text-3xl | 30 | 1.875 | 1.3 | H4 |
| text-4xl | 36 | 2.25 | 1.2 | H3 |
| text-5xl | 48 | 3 | 1.2 | H2 |
| text-6xl | 60 | 3.75 | 1.1 | H1 |

### Font Weights
| Token | Value | Usage |
|-------|-------|-------|
| font-normal | 400 | Body text |
| font-medium | 500 | Emphasis |
| font-semibold | 600 | Subheadings, buttons |
| font-bold | 700 | Headings |

### Font Families
```
font-sans: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", sans-serif
font-mono: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace
```

## Border Radius

| Token | px | Usage |
|-------|-----|-------|
| radius-none | 0 | Sharp corners |
| radius-sm | 4 | Subtle rounding |
| radius-md | 8 | **Standard components** |
| radius-lg | 12 | Cards, dialogs |
| radius-xl | 16 | Large cards |
| radius-2xl | 24 | Feature cards |
| radius-full | 9999 | Pills, avatars |

## Shadows

| Token | Value | Usage |
|-------|-------|-------|
| shadow-sm | 0 1px 2px rgba(0,0,0,0.05) | Subtle elevation |
| shadow-md | 0 4px 6px rgba(0,0,0,0.1) | Cards, dropdowns |
| shadow-lg | 0 10px 15px rgba(0,0,0,0.1) | Modals, popovers |
| shadow-xl | 0 20px 25px rgba(0,0,0,0.1) | Dialogs |

## Transitions

| Token | Value | Usage |
|-------|-------|-------|
| duration-fast | 100ms | Micro-interactions |
| duration-normal | 150ms | **Standard transitions** |
| duration-slow | 300ms | Page transitions |
| easing-default | ease | General purpose |
| easing-in | ease-in | Exit animations |
| easing-out | ease-out | Enter animations |
| easing-in-out | ease-in-out | Symmetric animations |

## Z-Index Scale

| Token | Value | Usage |
|-------|-------|-------|
| z-base | 0 | Default layer |
| z-dropdown | 1000 | Dropdowns, selects |
| z-sticky | 1100 | Sticky headers |
| z-fixed | 1200 | Fixed elements |
| z-modal-backdrop | 1300 | Modal overlays |
| z-modal | 1400 | Modal dialogs |
| z-popover | 1500 | Popovers, tooltips |
| z-toast | 1600 | Toast notifications |

## Breakpoints

| Token | px | Usage |
|-------|-----|-------|
| screen-sm | 640 | Small devices |
| screen-md | 768 | Tablets |
| screen-lg | 1024 | Small laptops |
| screen-xl | 1280 | Desktops |
| screen-2xl | 1536 | Large screens |

## Component Tokens

### Button
```
button-height-sm: 32px
button-height-md: 40px
button-height-lg: 48px
button-padding-x: spacing-4 (16px)
button-padding-y: spacing-2 (8px)
button-radius: radius-md (8px)
button-font-weight: font-semibold (600)
```

### Input
```
input-height: 40px
input-padding-x: spacing-3 (12px)
input-radius: radius-md (8px)
input-border-color: neutral-300
input-focus-ring: 2px solid primary-500
```

### Card
```
card-padding: spacing-6 (24px)
card-radius: radius-lg (12px)
card-shadow: shadow-md
card-background: white (dark: neutral-800)
```
