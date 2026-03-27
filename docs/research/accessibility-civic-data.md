# WCAG 2.1 AA accessibility patterns for the Influence Map component

Richmond Commons' Influence Map component — expandable campaign finance connection cards filtered by single-select toggle pills — maps cleanly onto established WAI-ARIA patterns. **Use the Disclosure pattern (Radix Collapsible) for card expand/collapse, a `role="group"` of `aria-pressed` toggle buttons for filters, and `<article>` elements inside a `<ul>` for the card list.** The primary Radix gotcha is ToggleGroup's broken role mapping in single mode (GitHub issue #3188), which requires manual ARIA overrides. California's ADA Title II deadline of **April 2026** makes WCAG 2.1 AA compliance immediately actionable for any platform associated with the City of Richmond.

This report covers all seven research areas with specific WCAG success criteria references, WAI-ARIA pattern citations, Radix primitive recommendations, and code examples.

---

## 1. Screen reader semantics for connection cards

**Use the HTML `<article>` element for each card, wrapped in `<li>` elements inside a `<ul>`.** The W3C APG Disclosure Card Example explicitly prescribes this structure: the `article` role enables screen reader users to perceive card boundaries and navigate between cards. The APG warns against `<section>`, which creates landmark regions — excessive landmarks diminish their utility. Do not use `role="article"` on a `<div>` when the native `<article>` element carries equivalent semantics (per WAI-ARIA structural roles guidance: "use native HTML elements wherever possible").

**Label each `<article>` with `aria-labelledby` pointing to the card's heading** — the plain-language connection statement (e.g., "Council Member Martinez voted yes on Budget Resolution"). This keeps the accessible name synchronized with visible text, satisfying **SC 2.5.3 Label in Name**. For the disclosure trigger button, use compound labeling: `aria-labelledby="card-heading-id btn-text-id"` so screen readers announce "Council Member Martinez voted yes on Budget Resolution, Evidence Details, button, collapsed."

**The card list container should be a `<ul>` (or `<ol>` if order is meaningful).** Per the NZ Government Web Accessibility Guide and Heydon Pickering's Inclusive Components, a list gives screen reader users information about how many cards exist. Do **not** use `role="feed"` unless you implement infinite scroll — the feed pattern is specifically for dynamically loading article lists and adds unnecessary complexity for static or paginated card sets.

**Badges (source tier, confidence) are static informational elements — not live regions.** Use `<span>` elements with visually hidden context text, not `role="status"`. The `role="status"` attribute creates a live region for dynamically changing content and would cause spurious announcements. The recommended pattern adds a screen-reader-only prefix for context:

```html
<span class="badge confidence-strong">
  <span class="sr-only">Confidence: </span>Strong
</span>
<span class="badge tier-1">
  <span class="sr-only">Source tier: </span>Tier 1
</span>
```

Applicable success criteria: **SC 1.3.1** (Info and Relationships — `<article>`, `<ul>`, heading hierarchy are programmatically determinable), **SC 4.1.2** (Name, Role, Value — article role, button states, badge names exposed to AT), **SC 2.4.6** (Headings and Labels — card heading describes topic).

---

## 2. Radix Collapsible is the correct expand/collapse primitive

**Use the WAI-ARIA Disclosure pattern, implemented via Radix Collapsible** — not Accordion. The W3C APG has a canonical "Disclosure Card" example that matches this exact use case. Each card's expand/collapse operates independently; no "only one expanded at a time" constraint exists. The Accordion pattern would impose arrow-key navigation between card triggers (Up/Down/Home/End), which is confusing when cards also contain links, buttons, and badges as interactive descendants.

| Criterion | Collapsible (Disclosure) | Accordion |
|-----------|-------------------------|-----------|
| Cards operate independently | ✅ Yes | ⚠️ Requires `type="multiple"` |
| Arrow key nav between triggers | ❌ Not expected | ✅ Required by pattern |
| W3C APG card example | ✅ Disclosure Card example | ❌ None |
| Heading structure required | No | Yes (`Accordion.Header`) |
| Content gets `role="region"` | No | Yes (adds landmarks) |

**Radix Collapsible automatically provides `aria-expanded` on the trigger and `aria-controls` pointing to the content panel.** It adheres to the Disclosure WAI-ARIA design pattern per its documentation. Keyboard interactions (Enter and Space to toggle) work out of the box. Note that Radix does **not** have a separate "Disclosure" primitive — Collapsible *is* their disclosure implementation.

**The expandable content section needs no special ARIA role.** It should be a plain `<div>` that is a direct child of the `<article>`. When collapsed, use the `hidden` attribute or `display: none` — both fully remove content from the tab order and accessibility tree. Never use `visibility: hidden` or `opacity: 0` alone, as these leave content accessible to screen readers. This is critical for **SC 2.4.3** (Focus Order): if a user can Tab into invisible content, it violates focus order requirements.

```tsx
<article aria-labelledby={headingId}>
  <h3 id={headingId}>{connection.statement}</h3>
  {/* Badges here — outside the trigger button */}
  <Collapsible.Root>
    <Collapsible.Trigger asChild>
      <button aria-labelledby={`${headingId} ${btnTextId}`}>
        <span id={btnTextId}>Evidence Details</span>
        <svg aria-hidden="true">{/* chevron */}</svg>
      </button>
    </Collapsible.Trigger>
    <Collapsible.Content>
      {/* Evidence text, source documents, action links */}
    </Collapsible.Content>
  </Collapsible.Root>
</article>
```

If the design later requires only-one-open-at-a-time behavior, switch to Radix Accordion with `type="single" collapsible` — but be aware this adds mandatory arrow-key navigation and heading structure requirements.

---

## 3. Color-plus-text satisfies WCAG 1.4.1, but three more SCs apply

**WCAG SC 1.4.1 (Use of Color, Level A) is satisfied by the existing text+color pairing.** The criterion requires that color is not the *sole* means of conveying information. Since the badges display visible text ("Strong", "Moderate", "Low", "Tier 1"–"Tier 4"), the non-color alternative already exists. No additional ARIA attributes are required specifically for SC 1.4.1 compliance.

**However, three additional success criteria govern badge appearance:**

**SC 1.4.3 (Contrast Minimum, AA)** requires badge text to have **4.5:1** contrast against the badge background. Yellow badges are the critical risk — white or light text on yellow almost always fails. Use dark text (near-black) on yellow backgrounds. Green and red backgrounds typically pass with white text, but verify your specific shades with a contrast checker.

**SC 1.4.11 (Non-text Contrast, AA)** requires the badge itself to have **3:1** contrast against adjacent colors (typically the white card background). A light yellow badge on a white card may fail this threshold. Add a visible border or use a sufficiently dark shade.

**SC 1.1.1 (Non-text Content, A)** requires text alternatives for any icons used in badges. Mark decorative icons with `aria-hidden="true"`.

**Triple redundancy (color + text + icon) is not required but strongly recommended.** Adding distinct icons per level — a checkmark for Strong, a warning triangle for Moderate, an X for Low — provides an additional visual channel that helps users with color vision deficiency. For source tier badges, consider distinct border styles or shield-variant icons. The green/yellow/red palette is one of the **most problematic combinations for the ~8% of men with red-green color vision deficiency**, even though text labels prevent information loss. If redesign is possible, blue/yellow/red provides better CVD differentiation due to lightness variation.

**No special ARIA role is needed for static badges.** They are non-interactive inline elements — `<span>` is semantically correct. Do not add `role="status"` (which creates live region announcements), `tabindex` (badges should not be focusable), or `<button>`/`<a>` (badges are not interactive). The visually hidden prefix pattern ("Confidence: Strong") provides sufficient programmatic context.

---

## 4. "Provide context" is a button, "View filing" is a link

The distinction is definitive: **elements that trigger actions on the current page are buttons; elements that navigate to a URL are links.** This principle comes directly from WAI-ARIA Authoring Practices and is reinforced by Adrian Roselli's canonical guidance.

**"Provide context" → `<button>` element.** It opens a modal or form — a state change on the current page. Use `aria-haspopup="dialog"` to tell screen readers a dialog will appear. If using Radix Dialog, its `Dialog.Trigger` renders a button by default with proper ARIA management. The keyboard behavior difference matters: `<button>` fires on both Enter and Space, while `<a>` fires on Enter only — using a link for a modal trigger means Space scrolls the page instead of opening the modal.

**"View filing" → `<a href="...">` element.** It navigates to an external government filing document. If it opens in a new tab, three elements are required: a visual external-link icon, screen-reader-only text "(opens in a new tab)", and `rel="noopener noreferrer"`. Screen readers do **not** automatically announce `target="_blank"` — NVDA, JAWS, and VoiceOver all fail to indicate new-tab behavior without explicit developer intervention.

**Contextual labeling for repeated actions across cards** is required by **SC 2.4.4** (Link Purpose in Context). When multiple cards each have "View filing" and "Provide context," use `aria-describedby` pointing to the card heading — this adds supplementary context without overriding the visible text (which would risk violating **SC 2.5.3** Label in Name):

```html
<h3 id="filing-123">Council Member Martinez voted yes on Budget Resolution</h3>
<!-- ...card content... -->
<button aria-haspopup="dialog" aria-describedby="filing-123">Provide context</button>
<a href="https://..." aria-describedby="filing-123">
  View filing
  <span class="sr-only">(opens in a new tab)</span>
</a>
```

**When a card is collapsed, all interactive descendants must be unreachable.** The `hidden` attribute or `display: none` on the Collapsible.Content container automatically removes buttons and links from the tab order. If using CSS animations that require the element to remain in the DOM, apply `inert` (modern browsers) or manually set `tabindex="-1"` plus `aria-hidden="true"` on every focusable descendant. A focusable element inside an `aria-hidden="true"` container is a common axe-core failure.

**Never nest interactive elements inside other interactive elements.** The expand/collapse trigger must be a `<button>` *inside* the card, not the card itself. Badges, action buttons, and links must be siblings of the trigger — not children of it. The HTML spec and ARIA both prohibit interactive nesting, and assistive technologies cannot determine which element should receive focus or activation.

---

## 5. Toggle filter pills need manual ARIA overrides on Radix ToggleGroup

**Radix ToggleGroup in `type="single"` mode has a known ARIA spec violation (GitHub issue #3188, still open).** The root renders `role="group"` while items render `role="radio"` — but per the WAI-ARIA spec, `role="radio"` elements **must** be contained in `role="radiogroup"`, not `role="group"`. This causes VoiceOver to fail to announce item positions ("1 of 3").

**The deeper problem: radiogroup semantics forbid deselection.** Per the ARIA spec, radio buttons cannot be unchecked — yet the design requires click-to-clear (deselect the active pill to show all results). The correct semantic model is a group of toggle buttons using `aria-pressed="true/false"`, which naturally supports on/off toggling.

**Recommended override strategy:**

```tsx
<ToggleGroup.Root
  type="single"
  value={activeFilter}
  onValueChange={setActiveFilter}
  role="group"
  aria-label="Filter by topic"
  aria-describedby="filter-instructions"
>
  {topics.map(({ name, count }) => (
    <ToggleGroup.Item
      key={name}
      value={name}
      aria-label={`${name}, ${count} results`}
      // Radix sets role="radio" internally — override via rendered props
    >
      <span aria-hidden="true">{name} · {count}</span>
    </ToggleGroup.Item>
  ))}
</ToggleGroup.Root>
```

Use `aria-label` on each pill to provide clean screen reader output ("Chevron, 2 results") while hiding the visual middle-dot separator from AT with `aria-hidden="true"`. Without this, screen readers may announce "Chevron middle dot 2" or "Chevron dot 2."

**Keyboard navigation works correctly out of the box.** Radix ToggleGroup implements roving tabindex by default: Tab enters/exits the group as a single tab stop, arrow keys move focus between pills, Enter/Space toggles the pressed state, and Home/End jump to first/last item. This matches the expected toolbar/group keyboard model.

**Filter result announcements require a `role="status"` live region** per **SC 4.1.3** (Status Messages, AA). Pre-render an empty container in the DOM at page load, then inject status text dynamically on filter change:

```tsx
<div role="status" aria-live="polite" aria-atomic="true">
  {activeFilter
    ? `Showing ${filteredCards.length} results for ${activeFilter}`
    : `Showing all ${cards.length} results`}
</div>
```

Do **not** wrap the entire results list in `aria-live` — live regions only communicate flat text strings, and semantic structure (links, headings) inside is lost. For zero-result states, escalate to `aria-live="assertive"` with `role="alert"` for immediate announcement.

---

## 6. California's ADA Title II deadline makes WCAG 2.1 AA mandatory by April 2026

**Section 508 does not directly apply to non-federal civic tech platforms**, but the legal landscape for Richmond Commons is shaped by three converging requirements. The **ADA Title II Final Rule** (28 CFR Part 35, Subpart H, published April 24, 2024) requires all state and local government web content to conform to **WCAG 2.1 Level AA**. Richmond, CA's population of ~116,000 places it in the **April 24, 2026 compliance deadline** tier. If Richmond Commons is used by or partnered with the City of Richmond, it falls under the city's obligation to ensure accessibility of its services and programs — including third-party contractor platforms.

**California adds additional layers.** The state's webstandards.ca.gov now references **WCAG 2.2 AA** — stricter than the federal requirement. California Government Code §§ 7405 and 11135 extend Section 508 requirements to entities receiving state funding. Most significantly, the **Unruh Civil Rights Act** (Civil Code § 51) applies to *all* California businesses, treats ADA violations as automatic Unruh violations, and carries **minimum $4,000 per violation** in statutory damages. California accounts for a disproportionate share of ADA web accessibility lawsuits nationally.

**The FEC.gov redesign (built with 18F) is the closest model for accessible campaign finance data.** It implements searchable, filterable data tables with proper semantic markup, plain-language summaries of complex financial data, and bulk download options. The platform commits to both WCAG AA conformance and the Plain Writing Act of 2010. Richmond Commons' "plain-language connection statements" align perfectly with federal plain language best practices and should target an **8th-grade reading level** for maximum accessibility.

For civic tech specifically, the 18F Accessibility Guide provides a prioritized checklist, and the U.S. Web Design System (USWDS) offers accessible table components with 11 manual accessibility tests. Both are directly applicable to campaign finance data presentation. **142 municipalities have been sued** over accessibility non-compliance since 2011 — the enforcement landscape is active and growing.

---

## 7. Radix primitive mapping and known conflicts

| UI element | Radix primitive | WAI-ARIA pattern | Manual overrides needed |
|-----------|----------------|-----------------|----------------------|
| Filter pill set | `ToggleGroup.Root` (`type="single"`) | Group of toggle buttons | Override to `role="group"`, override item roles to use `aria-pressed` |
| Individual pill | `ToggleGroup.Item` | Toggle button | Add `aria-label` with count context |
| Card expand/collapse | `Collapsible` | Disclosure | Add `aria-controls` manually (not auto-generated); add compound `aria-labelledby` |
| "Provide context" modal | `Dialog` (trigger + content) | Modal dialog | Provide `aria-label` or `aria-labelledby` on Dialog.Content |
| "View filing" link | Native `<a href>` | Link | No Radix primitive needed |
| Badge explanation | `Tooltip` (with caveats) or `Popover` | Tooltip / non-modal dialog | See known issues below |

**Radix Collapsible** works well out of the box. It automatically sets `aria-expanded` on the trigger and generates `aria-controls` pointing to the Content element. Keyboard handling (Enter/Space) is built in. The `data-state="open"|"closed"` attributes enable CSS animations via the `--radix-collapsible-content-height` variable.

**Radix ToggleGroup** requires the most intervention. Beyond the `role="group"` + `role="radio"` mismatch (issue #3188), the deselectable single-select pattern conflicts with radiogroup semantics. An alternative approach: use individual `Toggle.Root` components (which use `aria-pressed` by default) inside a manual `role="group"` wrapper with custom single-select state management. This avoids fighting ToggleGroup's internal role assignments.

**Radix Tooltip has multiple known WCAG 1.4.13 violations.** Issue #620 (labeled "Priority: Urgent") documents that tooltip content disappears when users move their pointer to hover over it — WCAG requires shown content to remain visible while the pointer is over it. Mobile touch support is also broken (issues #1351, #2589). If badge explanations need interactive content or mobile support, use **Radix Popover** instead, which provides a non-modal dialog without these limitations. Additionally, composing Tooltip with ToggleGroup causes `data-state` attribute clashes (issue #2029).

**Radix Dialog** handles focus management, Escape-to-close, and scroll locking automatically. Use it for the "Provide context" modal. The `Dialog.Trigger` renders a button with proper ARIA by default. You must provide `aria-label` or `aria-labelledby` on `Dialog.Content` — this is not auto-generated.

---

## Conclusion

The Influence Map component's accessibility architecture rests on three foundational patterns: the **Disclosure pattern** (Radix Collapsible) for card expand/collapse, **`<article>` in `<ul>`** for the card list structure, and a **group of toggle buttons** (Radix ToggleGroup with overrides) for filtering. The most significant implementation risk is Radix ToggleGroup's ARIA role mismatch in single mode — this requires either manual role overrides or a custom implementation using individual Toggle primitives.

The existing design decision to pair color with text on badges satisfies SC 1.4.1 without further work, but yellow badges likely fail contrast checks against white backgrounds (SC 1.4.3, 1.4.11) and should be verified. Adding distinct icons per confidence/tier level provides valuable triple redundancy for the **8% of male users with color vision deficiency**.

California's convergent accessibility requirements — the ADA Title II April 2026 deadline, WCAG 2.2 AA state standards, and Unruh Act exposure — make this not just best practice but legal necessity. The FEC.gov/18F model provides a proven blueprint for accessible campaign finance data presentation, and Richmond Commons' plain-language connection statements are a strong cognitive accessibility feature that should be maintained at an 8th-grade reading level.