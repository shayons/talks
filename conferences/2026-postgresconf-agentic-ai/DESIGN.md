---
name: Coffee & queries
description: Warm coffee-shop paper with inspectable PostgreSQL search evidence.
colors:
  primary: "#6b3f2a"
  primary-hover: "#523020"
  primary-fg: "#f6f1e8"
  bg: "#f6f1e8"
  bg-warm: "#efe6d8"
  surface: "#fffbf4"
  surface-2: "#f3ebe0"
  fg: "#1c1410"
  muted: "#6b5d52"
  subtle: "#736356"
  border: "#e2d6c6"
  border-strong: "#cbb9a4"
  keyword: "#3d4a52"
  keyword-soft: "#dce3e6"
  vector: "#3f5c4b"
  vector-soft: "#d5e2d8"
  hybrid: "#6b3f2a"
  hybrid-soft: "#ead9cf"
  danger: "#8f2d2d"
  warn: "#8a5a2a"
  warn-soft: "#f3e4cf"
  ok: "#3f5c4b"
  ok-soft: "#d5e2d8"
typography:
  display:
    fontFamily: '"Fraunces", "Times New Roman", serif'
    fontSize: "clamp(28px, 3.3vw, 38px)"
    fontWeight: 500
    lineHeight: 1.15
    letterSpacing: "-0.025em"
  headline:
    fontFamily: '"Fraunces", "Times New Roman", serif'
    fontSize: "26px"
    fontWeight: 500
    lineHeight: 1.2
    letterSpacing: "-0.025em"
  body:
    fontFamily: '"Source Sans 3", "Segoe UI", sans-serif'
    fontSize: "16px"
    lineHeight: 1.5
  label:
    fontFamily: '"Source Sans 3", "Segoe UI", sans-serif'
    fontSize: "14px"
  code:
    fontFamily: '"IBM Plex Mono", ui-monospace, monospace'
    fontSize: "12px"
    lineHeight: 1.65
rounded:
  chip: "4px"
  control: "8px"
  evidence: "10px"
  result: "12px"
  paper: "16px"
  concierge-shell: "18px"
spacing:
  compact: "8px"
  small: "12px"
  medium: "16px"
  large: "24px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.primary-fg}"
    rounded: "{rounded.control}"
    padding: "11px 16px"
  button-primary-hover:
    backgroundColor: "{colors.primary-hover}"
  button-quiet:
    backgroundColor: "{colors.surface-2}"
    textColor: "{colors.fg}"
    rounded: "{rounded.control}"
    padding: "11px 16px"
  input:
    backgroundColor: "{colors.bg}"
    textColor: "{colors.fg}"
    rounded: "{rounded.control}"
    padding: "10px 12px"
  paper:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.fg}"
    rounded: "{rounded.paper}"
    padding: "22px"
---

# Design System: Coffee & queries

## Overview

**Creative North Star: "Coffee & queries"**

Warm cream paper, illustrated coffee bags, and portraits make a technical search lab feel familiar. Expressive serif headings introduce people and products; compact interface text and precise measurements support close inspection. Lab, Catalog, Experiments, and Concierge share this identity and a common navigation shell.

The visual system is implemented in [static/index.html](static/index.html) and [static/lab.css](static/lab.css). The frontmatter records its reusable values; page-specific exceptions remain in the source.

## Colors

Coffee brown is the primary action color. Slate keyword, forest vector, and coffee-brown hybrid accents identify retrieval methods; their pale companions fill rank badges, score chips, and evidence blocks. Preserve these meanings across pages and pair color with visible labels.

Cream backgrounds and lighter paper surfaces provide most separation. Dark espresso text carries primary content, while muted brown supports metadata and labels. Use the stronger border for fields and the lighter border for dividers. Red, amber, and green communicate error, warning, and successful states alongside explanatory text.

## Typography

Fraunces carries the brand, page headings, customer names, coffee names, and large experiment metrics. Source Sans 3 carries navigation, controls, descriptions, and supporting facts. IBM Plex Mono carries SQL, query plans, rank arithmetic, and compact telemetry.

Use the display and headline roles for the main hierarchy. Product and subsection titles generally range from 17–23px; supporting text ranges from 12–15px. Keep introductory paragraphs comfortably bounded, as in the page-heading measure of 78ch. Prices and tabular measurements use aligned numerals. Uppercase, widely spaced labels belong to compact concierge telemetry, rather than general navigation or body copy.

## Layout

The centered application container has a maximum width of 1328px and horizontal padding of 24px. The shared header places the brand first, conference metadata next, and four navigation links at the end. Preserve the Postgres Summit US 2026 · NYC identity in the shell.

The Lab compares three equal ranking columns beneath shared filters. Catalog uses a selectable list beside a sticky detail panel. Experiments group controls with the evidence they affect. Concierge pairs the conversation with its architecture and database trace. Gaps commonly use the frontmatter spacing scale; paper containers use generous internal padding.

At 850px, filters become two columns. At 640px, container padding reduces to 16px, navigation occupies its own row, regulars and detail layouts stack, and the ranking comparison becomes a visible method switch showing one method at a time. The catalog list scrolls above its detail panel. Concierge stacks conversation and telemetry at 1100px. Long SQL and tables scroll within their own containers.

## Elevation & Depth

Depth is shallow and paper-like. Large surfaces use the shared shadow: `0 0 0 1px rgba(28, 20, 16, 0.06), 0 1px 2px -1px rgba(28, 20, 16, 0.06), 0 2px 4px 0 rgba(28, 20, 16, 0.04)`. Nested results and evidence generally rely on tonal fills. Selected items use a brown outline; depth never substitutes for selection feedback.

## Shapes

Soft rectangles organize the interface. Broad paper surfaces have roomier corners than controls, result rows, evidence blocks, and small chips. Portraits and packaging thumbnails retain rounded crops. Pills are reserved for existing compact identity and status controls in Concierge. Fine dividers separate related sections without enclosing every fact in another card.

## Components

- **Actions and fields:** primary buttons use brown with cream text; quieter actions use a pale neutral fill. Main search controls have a minimum height of 44px. Fields have a stronger neutral border. Keep visible labels, brown checkbox/range accents, disabled feedback, and the shared focus outline of 2px with a 3px offset.
- **Navigation and switches:** the active page has a pale filled background. Inspector and mobile method switches use a raised paper selection inside a neutral track. Preserve visible names and programmatic current or pressed states.
- **Regulars and coffee rows:** place an illustration beside a serif name and short supporting facts. Selection adds a brown outline. Packaging remains illustrative; live product names, prices, and stock appear as readable text beside it.
- **Ranking evidence:** retain labeled keyword, vector, and hybrid scores, rank badges, and explicit fusion arithmetic. Exclusions and empty results belong within the comparison. SQL and EXPLAIN use the mono role on a dark inset surface.
- **Catalog dimensions and experiments:** embedding cells encode numeric sign and magnitude, with inspectable values nearby. Tables align measurements and distinguish recovered neighbors with labeled context. Keep experiment controls adjacent to outcomes and explanatory states.
- **Concierge:** preserve the conversation and trace relationship, illustrated product recommendations, restrained tabs, and clear pending, interrupted, and error treatments. Small hover movement is brief; honor the existing reduced-motion override.

## Do's and Don'ts

- **Do** retain the cream paper, coffee-brown controls, three-font hierarchy, and consistent retrieval colors.
- **Do** preserve keyboard focus, readable status text, mobile method selection, and access to detailed evidence.
- **Do** use PostgreSQL results for displayed catalog facts and search measurements.
- **Don't** treat illustrative packaging as the source of a product's identity or availability.
- **Don't** invent flavor labels for embedding dimensions or present simulated timings as measured results.
- **Don't** let color alone distinguish methods, selections, or failure states.
