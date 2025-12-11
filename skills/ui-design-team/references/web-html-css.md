# Web Platform Specialist (HTML/CSS)

Translate design specifications into semantic HTML5 and modern CSS.

## Core Competencies

### Semantic HTML5
- **Structure**: header, nav, main, aside, footer, article, section
- **Headings**: Logical h1-h6 hierarchy
- **Forms**: Correct input types, labels, fieldsets
- **Interactive**: button (actions) vs anchor (navigation) vs div (never for interaction)
- **ARIA**: Use when native semantics insufficient

### CSS Architecture
- **BEM naming**: `.block__element--modifier`
- **Custom properties**: Design tokens as CSS variables
- **Specificity**: Keep flat, avoid !important, use @layer for organization
- **Scope**: CSS Modules or scoped styles for components

### Layout Systems

**CSS Grid** (2D layouts):
```css
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: var(--spacing-md);
}
```

**Flexbox** (1D layouts):
```css
.flex-row {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}
```

### Responsive Design
- **Mobile-first**: Start small, enhance up
- **Breakpoints**: Content-driven, not device-driven
- **Fluid typography**: `clamp(1rem, 2.5vw, 1.5rem)`
- **Container queries**: Component-based responsiveness

### Accessibility Implementation
- **Focus**: `:focus-visible` with visible outline
- **Reduced motion**: `@media (prefers-reduced-motion: reduce)`
- **High contrast**: `@media (forced-colors: active)`
- **Screen readers**: Visually hidden text when needed

## Design Token Implementation

```css
:root {
  /* Colors */
  --primary-500: #3b82f6;
  --primary-600: #2563eb;
  --neutral-50: #f9fafb;
  --neutral-900: #111827;
  
  /* Semantic */
  --color-background: var(--neutral-50);
  --color-surface: white;
  --color-text-primary: var(--neutral-900);
  --color-border: var(--neutral-200);
  
  /* Spacing */
  --spacing-xs: 0.25rem;
  --spacing-sm: 0.5rem;
  --spacing-md: 1rem;
  --spacing-lg: 1.5rem;
  
  /* Typography */
  --font-family: system-ui, -apple-system, sans-serif;
  --font-size-base: 1rem;
  --line-height-normal: 1.5;
  
  /* Borders */
  --radius-md: 0.5rem;
}

/* Dark mode */
@media (prefers-color-scheme: dark) {
  :root {
    --color-background: var(--neutral-900);
    --color-surface: var(--neutral-800);
    --color-text-primary: var(--neutral-50);
  }
}
```

## Component Template

```html
<!-- Component: Button
     Accessibility: Focusable, labeled, keyboard-operable -->
<button class="btn btn--primary" type="button">
  <span class="btn__text">Action</span>
</button>
```

```css
.btn {
  /* Reset */
  appearance: none;
  border: none;
  cursor: pointer;
  
  /* Layout */
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-xs);
  
  /* Sizing */
  padding: var(--spacing-sm) var(--spacing-md);
  min-height: 44px; /* Touch target */
  
  /* Typography */
  font-family: var(--font-family);
  font-size: var(--font-size-base);
  font-weight: 600;
  
  /* Visual */
  border-radius: var(--radius-md);
  transition: background-color 150ms ease;
}

.btn--primary {
  background: var(--primary-500);
  color: white;
}

.btn--primary:hover {
  background: var(--primary-600);
}

.btn--primary:focus-visible {
  outline: 2px solid var(--primary-500);
  outline-offset: 2px;
}

.btn--primary:active {
  transform: scale(0.98);
}

.btn--primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
```

## Performance Considerations
- **Critical CSS**: Inline above-fold styles
- **Efficient selectors**: Avoid deep nesting
- **GPU acceleration**: Use transform/opacity for animations
- **Content-visibility**: For long pages

## Browser Compatibility
- **Feature detection**: `@supports` for progressive enhancement
- **Logical properties**: `margin-inline`, `padding-block` for i18n
- **Fallbacks**: Provide alternatives for cutting-edge features

## Output Standards

1. Valid HTML5 (passes W3C validation)
2. Semantic structure (appropriate elements)
3. BEM or consistent naming convention
4. Design tokens as CSS variables (no magic numbers)
5. All states implemented (default, hover, focus, active, disabled)
6. Responsive breakpoints included
7. Accessibility compliant (focus visible, sufficient contrast)
