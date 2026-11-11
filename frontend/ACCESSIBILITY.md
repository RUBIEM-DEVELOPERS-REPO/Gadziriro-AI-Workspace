# Accessibility (WCAG 2.1 AA, FR-43)

Measures applied across the whole frontend:

- **Document**: `<html lang="en">` and a page `<title>` in `index.html`; a "Skip to main content" link as the first focusable element.
- **Tabs**: main navigation uses `role="tablist"` / `role="tab"` / `role="tabpanel"` with `aria-selected`, `aria-controls`, and roving `tabIndex`. Arrow Left/Right, Home and End move focus and selection; Enter/Space activate. The panel is labelled by the active tab.
- **Forms**: every input, select and textarea has a programmatically associated `<label htmlFor>` (or a wrapping label, or `aria-label` for table-row inputs such as the Evaluate suite). Non-input captions use `.field-label` spans rather than orphan `<label>`s.
- **Buttons / names**: all buttons have visible text or an `aria-label` (e.g. "Remove row 2"). No images or icon-only controls are used; empty header cells carry screen-reader text.
- **Tables**: new tables have `<caption class="sr-only">` and `scope="col"` headers; wide tables scroll horizontally instead of clipping.
- **Live regions**: errors use `role="alert"`; async results and loading states use `role="status"` / `aria-live="polite"` (updates, ACL save, egress report, safety results, DPIA changes, audit verify, licence check).
- **Focus**: a 2px high-visibility `:focus-visible` outline (offset 2px) on all interactive elements; outlines are never removed without a replacement.
- **Contrast**: text/background pairs checked to at least 4.5:1. Primary buttons use `--accent-btn` (#2563eb, 5.2:1 with white) instead of the lighter accent (3.2:1); danger/broken text lightened to #f2666b (>= 4.4:1 on the darkest panel, ~4.8:1 on page background); form control borders use `--input-border` (#7b8494) for the 3:1 non-text contrast requirement.
- **Colour is not the only signal**: status badges always carry text (OK, BROKEN, approved, blocked, passed, failed).
- **Motion**: `prefers-reduced-motion` disables animations and transitions.
