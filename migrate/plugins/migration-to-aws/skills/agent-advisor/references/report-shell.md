# Shared report shell — visual chrome & components

A single source of truth for the shared visual system of every HTML report in this skill
(recommendation-report.html, poc-report.html, temporal-migration-report.html): the reset,
page layout, dark site-header, hero panel, KPI stat tiles, chips, timeline, icon feature
grid, alert banners, base table, section titles, and footer. Keeping it here means these
rules are maintained in ONE place, so the reports stop drifting.

Content-specific CSS (score bars, service tags, diagram cards, cost cards, etc.) does NOT
live here — each report keeps its own content rules in its own generator, ADDED AFTER this
block. Never restate a shell rule locally.

## Chart color tokens (validated)

The two chart fill colors are design-system constants, validated with the dataviz
six-checks palette validator on the light card surface (lightness band PASS, CVD ΔE 66+
PASS; the muted tone is a deliberate de-emphasis, and every bar always carries a visible
value label, which satisfies the contrast-relief obligation):

- `--chart-accent: #C77700` — the WINNER / primary magnitude fill. (NOT `#FF9900`: raw AWS
  orange fails 3:1 contrast on white. `#FF9900` is reserved for chrome on DARK surfaces —
  hero eyebrow/badges, buttons — where it has ample contrast.)
- `--chart-muted: #94a3b8` — every de-emphasized bar/track mark.

## CSS (inline this block into each report's `<style>` block)

```css
  :root { --chart-accent: #C77700; --chart-muted: #94a3b8; }

  /* ── Reset & base ── */
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
         background: #f4f6f8; color: #1a1a2e; font-size: 15px; line-height: 1.6; }

  /* ── Layout ── */
  .page { max-width: 1100px; margin: 0 auto; padding: 0 24px 80px; }

  /* ── Header (slim brand bar) ── */
  .site-header { background: #1a1a2e; color: #fff; padding: 16px 0; }
  .site-header .inner { max-width: 1100px; margin: 0 auto; padding: 0 24px;
                         display: flex; justify-content: space-between; align-items: center; }
  .site-header h1 { font-size: 17px; font-weight: 600; letter-spacing: -0.2px; }
  .site-header .meta { font-size: 12px; color: #8892a4; text-align: right; }

  /* ── Hero panel (the report's single headline block — exactly ONE per report) ── */
  .hero-panel { background: linear-gradient(135deg, #1a1a2e 0%, #2d2b55 100%);
                border-radius: 16px; padding: 36px 40px; margin-top: 24px; color: #fff; }
  .hero-eyebrow { font-size: 11px; font-weight: 700; text-transform: uppercase;
                  letter-spacing: 1.4px; color: #FF9900; margin-bottom: 10px; }
  .hero-verdict { font-size: 40px; font-weight: 800; letter-spacing: -0.8px;
                  line-height: 1.15; }
  .hero-verdict small { font-size: 18px; font-weight: 600; color: #aeb4c4;
                        letter-spacing: 0; display: block; margin-top: 4px; }
  .hero-lead { font-size: 16px; color: #c7cbd6; margin-top: 14px; max-width: 46em; }
  .hero-badges { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 20px; }
  .badge { font-size: 12px; font-weight: 600; color: #FF9900; padding: 4px 12px;
           border: 1px solid rgba(255,153,0,.45); border-radius: 999px; }
  .badge.neutral { color: #c7cbd6; border-color: rgba(199,203,214,.35); }

  /* ── KPI stat-tile row (label / value / note; values use proportional figures —
        do NOT set tabular-nums on a display-size value) ── */
  .kpi-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
             gap: 12px; margin-top: 16px; }
  .kpi { background: #fff; border: 1px solid #eef0f3; border-radius: 12px;
         padding: 16px 18px; box-shadow: 0 1px 3px rgba(0,0,0,.04); }
  .kpi-label { font-size: 11px; font-weight: 600; color: #6b7280;
               text-transform: uppercase; letter-spacing: 0.6px; }
  .kpi-value { font-size: 23px; font-weight: 650; color: #1a1a2e; margin-top: 4px;
               line-height: 1.2; }
  .kpi-note { font-size: 12px; color: #9ca3af; margin-top: 2px; }

  /* ── Chips (profile facts, tags) ── */
  .chip-row { display: flex; flex-wrap: wrap; gap: 8px; }
  .chip { display: inline-flex; align-items: center; gap: 6px; font-size: 12.5px;
          color: #374151; background: #eef2f7; border: 1px solid #e2e8f0;
          border-radius: 999px; padding: 4px 12px; }
  .chip strong { color: #1a1a2e; font-weight: 650; }

  /* ── Card base (all white content blocks) ── */
  .card { background: #fff; border: 1px solid #eef0f3; border-radius: 12px;
          padding: 24px 28px; box-shadow: 0 1px 3px rgba(0,0,0,.04); }

  /* ── Section titles ── */
  .section-title { font-size: 13px; font-weight: 700; text-transform: uppercase;
                   letter-spacing: 0.8px; color: #6b7280; margin: 40px 0 14px; }

  /* ── Icon feature grid (e.g. capability dimensions) ── */
  .feat-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
               gap: 12px; }
  .feat { display: flex; gap: 12px; align-items: flex-start; background: #fff;
          border: 1px solid #eef0f3; border-radius: 12px; padding: 14px 16px; }
  .feat-icon { flex: none; width: 30px; height: 30px; border-radius: 8px;
               background: #1a1a2e; color: #fff; display: flex; align-items: center;
               justify-content: center; font-size: 15px; }
  .feat-name { font-size: 13px; font-weight: 700; color: #1a1a2e; }
  .feat-desc { font-size: 12px; color: #6b7280; line-height: 1.45; margin-top: 1px; }

  /* ── Timeline (numbered next steps) ── */
  .timeline { display: flex; flex-direction: column; }
  .tstep { display: flex; gap: 16px; position: relative; padding-bottom: 22px; }
  .tstep:last-child { padding-bottom: 0; }
  .tstep::before { content: ""; position: absolute; left: 13px; top: 30px; bottom: 2px;
                   width: 2px; background: #e5e7eb; }
  .tstep:last-child::before { display: none; }
  .tnum { flex: none; width: 28px; height: 28px; border-radius: 50%; background: #1a1a2e;
          color: #fff; font-size: 13px; font-weight: 700; display: flex;
          align-items: center; justify-content: center; }
  .tstep-title { font-size: 14px; font-weight: 700; color: #1a1a2e; }
  .tstep-body { font-size: 13px; color: #4b5563; margin-top: 2px; }
  .tstep-body code, .tstep-body pre { font-size: 12px; background: #f6f8fa;
          border: 1px solid #eef0f3; border-radius: 6px; padding: 1px 6px; }

  /* ── Alert banners ── */
  .banner { border-radius: 8px; padding: 14px 18px; margin-top: 20px;
            font-size: 14px; display: flex; gap: 12px; align-items: flex-start; }
  .banner.warning  { background: #fff7ed; border: 1px solid #fed7aa; color: #92400e; }
  .banner.info     { background: #eff6ff; border: 1px solid #bfdbfe; color: #1e40af; }
  .banner.tco      { background: #f0fdf4; border: 1px solid #bbf7d0; color: #166534; }
  .banner.fedramp  { background: #fef2f2; border: 1px solid #fecaca; color: #991b1b; }
  .banner-icon { font-size: 18px; flex-shrink: 0; }

  /* ── Base table ── */
  table { width: 100%; border-collapse: collapse; font-size: 14px; }
  th { background: #f9fafb; color: #6b7280; font-weight: 600; font-size: 12px;
       text-transform: uppercase; letter-spacing: 0.5px; padding: 10px 14px;
       text-align: left; border-bottom: 2px solid #e5e7eb; }
  td { padding: 10px 14px; border-bottom: 1px solid #f3f4f6; color: #374151; }
  tr:last-child td { border-bottom: none; }
  tbody tr:hover td { background: #fafbfc; }

  /* ── Two-col layout ── */
  .two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
  @media (max-width: 760px) { .two-col { grid-template-columns: 1fr; }
                              .hero-verdict { font-size: 30px; } }

  /* ── Footer ── */
  .report-footer { font-size: 12px; color: #9ca3af; margin-top: 44px;
                   padding-top: 16px; border-top: 1px solid #e5e7eb; }
```

## Mermaid script tag (part of the shared shell for any report with a diagram)

Any report that renders a Mermaid diagram loads the SAME SRI-pinned mermaid@10.9.3 script tag
in its `<head>` — copy it VERBATIM (the integrity hash must not change):

```html
<script src="https://cdn.jsdelivr.net/npm/mermaid@10.9.3/dist/mermaid.min.js"
        integrity="sha384-R63zfMfSwJF4xCR11wXii+QUsbiBIdiDzDbtxia72oGWfkT7WHJfmD/I/eeHPJyT"
        crossorigin="anonymous"></script>
```

## Usage note

Each report generator inlines the CSS block above into its own `<style>` block, then adds
its OWN content-specific rules after it. The union of (this shell + the report's own
content CSS) must reproduce that report's full rule set — do not drop or restyle a shared
rule locally, or the reports drift again.

Component contract (what each shared piece is FOR):

| Component                                    | Use                                                                                                                       |
| -------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| `.hero-panel` (+eyebrow/verdict/lead/badges) | the report's single headline: the verdict, a one-sentence plain-language lead, and status badges. Exactly ONE per report. |
| `.kpi-row` / `.kpi`                          | 3–5 stat tiles right under the hero: label + value (+optional note). Values in plain figures, auto-compact ($120–180/mo). |
| `.chip-row` / `.chip`                        | short facts: the profile answers that drove a decision, tags                                                              |
| `.card`                                      | the base white block every content section sits in                                                                        |
| `.feat-grid` / `.feat`                       | icon + name + one-liner grids (capability dimensions, file purposes)                                                      |
| `.timeline` / `.tstep`                       | numbered sequential steps (next steps, runbooks)                                                                          |
| `.banner.*`                                  | warnings / info / TCO / FedRAMP callouts                                                                                  |
| `--chart-accent` / `--chart-muted`           | the ONLY chart fill colors (see Chart color tokens above)                                                                 |

- **recommendation-report.html** — `references/phases/generate/generate-report.md` inlines
  this block plus its score-bar/service/diagram/alternatives/model content rules.
- **temporal-migration-report.html** — `references/phases/temporal-worker/temporal-worker.md`
  Step 5 inlines this block plus temporal-specific content rules; its headline uses
  `.hero-panel` + `.kpi-row` (Way, task queues, Activity classes), its tier tables use the
  shared `table`, its runbook the shared `.timeline`, its diagram the shared mermaid tag.
- **poc-report.html** — `references/phases/poc/poc-report.md`; its file map fits
  `.feat-grid`, its deploy steps fit `.timeline`.

The shared "Need help?" CTA banner is a separate single-source file
(`references/report-help-banner.md`); load it too. The shell here is the frame; the help
banner is the CTA that sits at the top of the page inside that frame.
