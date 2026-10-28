# M3b Visual Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restyle the M3 design system so it stops reading as AI-generated. The new look is flat, typographic and
civic, following UI UX Pro Max's government recommendation.

**Architecture:**
- **Behaviour is unchanged:** htmx, toasts, dialogs, bulk bar, nav toggle, tags, views and URLs stay as they are.
- **What changes:** tokens and fonts, the component and layout CSS, and the markup where the old look lived in
  templates (icon chips, icons inside pills and nav items, the sidebar shell).
- **Old classes become new ones:**
  - `.pill` becomes `.tag`;
  - `.stat` becomes `.figure`;
  - `.card` stays as the panel class but is restyled.
- **Tests:** existing behaviour tests keep passing. New markup tests pin the anti-patterns we removed, and screenshots
  are reviewed every task.

**Tech Stack:** existing M3 stack. Fonts change to `@fontsource/lexend` 5.3.0 and `@fontsource/source-sans-3`
5.3.1, replacing Inter and Poppins.

**Spec:** `docs/superpowers/specs/2026-10-11-scholarsync-v2-design.md` **rev 3 §12** (the design authority: exact colours,
type, shape, component and layout rules). The design source is the UI UX Pro Max skill (cloned read-only at
`<scratchpad>/uupm/repo`, commit `28b3b8d`). Its search tool is:

```
python "<scratchpad>/uupm/repo/.claude/skills/ui-ux-pro-max/scripts/search.py" "<query>" --domain <ux|style|typography|color>
```

It is stdlib-only and safe to run. Use it for focused UX questions (e.g. `"error summary validation" --domain ux`). Its
results are recommendations; spec §12 wins on any conflict.

**Note on step style:** this is a restyle, and the work is visual iteration against exact values. Each step gives the
exact values, the rules and the tests; the implementer writes the CSS and must check screenshots before committing.

## Global Constraints
- Everything in the M3 plan's Global Constraints still binds: CSP (no inline script/style, no `hx-on`), the htmx config,
  no-JS behaviour, 44 px targets, the WCAG 2.2 AA rules, Decimal `peso`, Windows shells, build before pytest, one commit
  per task, **no AI attribution**, never push.
- **Spec §12 rev 3 values, verbatim:**
  - **Colours:**
    - ink `#0e1b2c`, muted `#4b5563`, bg `#f5f4f0`, surface `#ffffff`, sunken `#ecebe6`, border `#d6d3cb`, control
      border `#5f6368`;
    - navy `#1a3a6b`, hover `#10284d`, tint `#e8eef7`;
    - red `#b8132a`, tint `#fbecee`; gold `#f0b323`;
    - success `#11663a` on `#e7f3ec`; warning `#8a4b00` on `#fbf1e2`;
    - nav muted text `#c9d4e6`.
  - **Type:** Lexend 500/600 headings; Source Sans 3 400/600 body at 1.0625rem, line height 1.55; tabular figures
    for money.
  - **Shape:** radius 3 px (controls, tags) and 4 px (panels, dialogs), never pill-shaped. No shadows except dialog,
    toast and menus.
  - **Colour roles:** red only for the brand mark and danger; actions in navy; gold only as the stripe, the
    active-nav marker and the focus halo (never text, never a background behind white text).
  - **Focus:** `outline: 3px solid var(--focus)` (ink) plus `box-shadow: 0 0 0 6px var(--focus-halo)` (gold),
    the halo outside the outline. On the navy top bar the halo carries the contrast (gold on navy 6:1).
- **Anti-patterns that must not come back** (UI UX Pro Max "avoid" + our AI tells): icon chips on figures; icons inside
  tags; icons on nav items; icons on buttons except download/close/menu/sign-out; gradients; pill radius; a shadow on
  panels; nested boxes (a panel inside a panel); ALL-CAPS labels; middle-dot meta strings.
- **Phone:** no horizontal page scroll at 375 px (the existing e2e tests check this).

## Review Focus
1. **Focus ring on dark and light surfaces:** keyboard focus on the navy top bar and on white panels must both be
   visible. Test: Task 1 contrast pairs (focus/surface, focus-halo/nav-bg) and a Task 4 e2e test that focuses a top-bar
   link and checks its computed outline and box-shadow are non-none.
2. **Status still readable without colour:** removing pill icons must not leave colour-only status. Every `.tag` has
   text. Test: Task 3 unit test that each rendered `.tag` in the kit and mockups has non-empty text and no `<svg>`.
3. **Money alignment:** figures and table amounts keep tabular figures in the new fonts. Test: Task 3 computed-style e2e
   check `font-variant-numeric` contains `tabular-nums` on `.figure__value` and `td.num`.
4. **Phone overflow:** the new top bar with the program switcher and user must fit at 375 px. Covered by the existing
   e2e layout/mockup overflow tests, which must keep passing.
5. **No-JS nav:** the restyled shells keep the nav visible without JS. Covered by the existing
   `test_nav_is_visible_without_javascript_on_a_phone`, which must keep passing.

---

### Task 1: Tokens, fonts and base

**Files:**
- Modify: `frontend/package.json`, `frontend/package-lock.json` (remove `@fontsource/inter` and `@fontsource/poppins`;
  add `@fontsource/lexend@5.3.0` and `@fontsource/source-sans-3@5.3.1`, exact)
- Rewrite: `frontend/src/styles/fonts.css`, `frontend/src/styles/tokens.css`
- Modify: `frontend/src/styles/base.css` (type, focus, utilities)
- Modify: `templates/base.html` (theme-color `#1a3a6b`)
- Modify: `tests/test_tokens.py` (pairs, font names), `tests/e2e/test_kit.py` (font names)

**Interfaces:**
- Produces:
  - **Palette tokens:** `--ink-900`, `--ink-600`, `--stone-50`, `--stone-100`, `--stone-300`, `--stone-600`,
    `--white`, `--navy-700`, `--navy-800`, `--navy-50`, `--navy-muted`, `--red-700`, `--red-50`, `--gold-400`,
    `--green-800`, `--green-50`, `--amber-800`, `--amber-50`.
  - **Role tokens:** `--text`, `--text-muted`, `--text-inverse`, `--bg`, `--surface`, `--surface-sunken`, `--border`,
    `--border-strong`, `--border-control`, `--primary`, `--primary-hover`, `--primary-50`, `--on-primary`, `--link`,
    `--link-hover`, `--brand`, `--danger`, `--danger-50`, `--success`, `--success-50`, `--warning`, `--warning-50`,
    `--info`, `--info-50`, `--accent`, `--focus`, `--focus-halo`, `--nav-bg`, `--nav-bg-hover`, `--nav-text`,
    `--nav-text-muted`, `--nav-marker`.
  - **Scale tokens:** `--font-heading`, `--font-body`, `--text-sm`…`--text-4xl`, `--leading-*`, `--measure`,
    `--space-*` (unchanged), `--radius-sm` (3px), `--radius-md` (3px), `--radius-lg` (4px), `--shadow-float`,
    `--control-height`, `--sidebar-width`, `--content-max`, `--duration`, `--ease`.
  - **Compatibility:** the old names `--brand-600`, `--brand-700`, `--brand-50`, `--info`, `--gray-*`,
    `--radius-full`, `--shadow-1`, `--shadow-2`, `--navy-muted` and `--accent-50` are **removed**. Tasks 2–4 replace
    every use; until then the build still succeeds and an unknown `var()` just falls back.

- [ ] **Step 1: Update the tests first**

In `tests/test_tokens.py`, replace `TEXT_PAIRS`, `NON_TEXT_PAIRS` and `DECORATIVE_AS_TEXT`:
```python
TEXT_PAIRS = [
    ("text", "surface"),
    ("text", "bg"),
    ("text", "surface-sunken"),
    ("text-muted", "surface"),
    ("text-muted", "bg"),
    ("text-muted", "surface-sunken"),
    ("link", "surface"),
    ("link", "bg"),
    ("link-hover", "primary-50"),
    ("on-primary", "primary"),
    ("on-primary", "primary-hover"),
    ("primary", "primary-50"),
    ("danger", "surface"),
    ("danger", "danger-50"),
    ("text-inverse", "danger"),
    ("success", "success-50"),
    ("warning", "warning-50"),
    ("info", "info-50"),
    ("nav-text", "nav-bg"),
    ("nav-text-muted", "nav-bg"),
    ("nav-text", "nav-bg-hover"),
    ("text", "accent"),
]
# Control borders, focus rings and markers must reach 3:1 (WCAG 1.4.11).
NON_TEXT_PAIRS = [
    ("border-control", "surface"),
    ("focus", "surface"),
    ("focus", "bg"),
    ("focus-halo", "nav-bg"),
    ("nav-marker", "nav-bg"),
    ("primary", "surface"),
]
DECORATIVE_AS_TEXT = re.compile(r"(?<![-\w])color:\s*var\(--(accent|gold-400|focus-halo|nav-marker)\)")
```
In `test_fonts_are_self_hosted`, assert `"Lexend" in css` and `"Source Sans 3" in css` instead of Inter/Poppins. In
`tests/e2e/test_kit.py`, assert `"Lexend"` and `"Source Sans 3"` are among the loaded families.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m uv run pytest tests/test_tokens.py -q`
Expected: FAIL with `KeyError: 'primary'` and missing font names.

- [ ] **Step 3: Swap the fonts**

```powershell
Push-Location frontend; npm uninstall @fontsource/inter @fontsource/poppins; npm install --save-dev --save-exact @fontsource/lexend@5.3.0 @fontsource/source-sans-3@5.3.1; Pop-Location
Select-String -Path frontend/package-lock.json -Pattern 'linux-x64-gnu' | Select-Object -First 1
```

`frontend/src/styles/fonts.css`:
```css
/* Self-hosted Latin subsets (spec §12 rev 3: UI UX Pro Max "Corporate Trust" pairing). No runtime CDN. */
@import "@fontsource/lexend/latin-500.css";
@import "@fontsource/lexend/latin-600.css";
@import "@fontsource/source-sans-3/latin-400.css";
@import "@fontsource/source-sans-3/latin-600.css";
```

- [ ] **Step 4: Write `tokens.css`**

```css
/* Design tokens (spec §12 rev 3). tests/test_tokens.py checks every pair the components use. */
:root {
  /* Palette */
  --ink-900: #0e1b2c;
  --ink-600: #4b5563;
  --stone-50: #f5f4f0;
  --stone-100: #ecebe6;
  --stone-300: #d6d3cb;
  --stone-600: #5f6368;
  --white: #ffffff;
  --navy-700: #1a3a6b;
  --navy-800: #10284d;
  --navy-50: #e8eef7;
  --navy-muted: #c9d4e6;
  --red-700: #b8132a; /* Taguig red: brand mark and danger only */
  --red-50: #fbecee;
  --gold-400: #f0b323; /* decorative only: civic stripe, nav marker, focus halo */
  --green-800: #11663a;
  --green-50: #e7f3ec;
  --amber-800: #8a4b00;
  --amber-50: #fbf1e2;

  /* Roles */
  --text: var(--ink-900);
  --text-muted: var(--ink-600);
  --text-inverse: var(--white);
  --bg: var(--stone-50);
  --surface: var(--white);
  --surface-sunken: var(--stone-100);
  --border: var(--stone-300);
  --border-strong: var(--ink-900);
  --border-control: var(--stone-600);
  --primary: var(--navy-700);
  --primary-hover: var(--navy-800);
  --primary-50: var(--navy-50);
  --on-primary: var(--white);
  --link: var(--navy-700);
  --link-hover: var(--navy-800);
  --brand: var(--red-700);
  --danger: var(--red-700);
  --danger-50: var(--red-50);
  --success: var(--green-800);
  --success-50: var(--green-50);
  --warning: var(--amber-800);
  --warning-50: var(--amber-50);
  --info: var(--navy-700);
  --info-50: var(--navy-50);
  --accent: var(--gold-400);
  --focus: var(--ink-900);
  --focus-halo: var(--gold-400);
  --nav-bg: var(--navy-700);
  --nav-bg-hover: var(--navy-800);
  --nav-text: var(--white);
  --nav-text-muted: var(--navy-muted);
  --nav-marker: var(--gold-400);

  /* Type: 17 px body, 1.25 scale */
  --font-heading: "Lexend", system-ui, sans-serif;
  --font-body: "Source Sans 3", system-ui, -apple-system, "Segoe UI", sans-serif;
  --text-sm: 0.9375rem;
  --text-base: 1.0625rem;
  --text-lg: 1.25rem;
  --text-xl: 1.5rem;
  --text-2xl: 1.875rem;
  --text-3xl: 2.25rem;
  --text-4xl: 2.875rem;
  --leading-tight: 1.2;
  --leading-body: 1.55;
  --measure: 68ch;

  /* Space: 4 px steps */
  --space-1: 0.25rem;
  --space-2: 0.5rem;
  --space-3: 0.75rem;
  --space-4: 1rem;
  --space-5: 1.25rem;
  --space-6: 1.5rem;
  --space-8: 2rem;
  --space-10: 2.5rem;
  --space-12: 3rem;
  --space-16: 4rem;

  /* Shape: small radii, never pills; shadows only on floating layers */
  --radius-sm: 3px;
  --radius-md: 3px;
  --radius-lg: 4px;
  --shadow-float: 0 12px 32px -8px rgb(14 27 44 / 0.3);

  /* Sizes and motion */
  --control-height: 2.75rem;
  --sidebar-width: 15rem;
  --content-max: 76rem;
  --duration: 150ms;
  --ease: cubic-bezier(0.2, 0, 0, 1);
}
```

- [ ] **Step 5: Base styles**

In `frontend/src/styles/base.css`:
- `body`: `font-size: var(--text-base)`, `line-height: var(--leading-body)`, `color: var(--text)`,
  `background: var(--bg)`.
- Headings `h1–h4, .h1–.h4`:
  - `font-family: var(--font-heading)`, `font-weight: 600`, `letter-spacing: -0.01em`;
  - `h1` uses `--text-3xl` (weight 600, not 700; Lexend is wide);
  - `h2` `--text-2xl`, `h3` `--text-xl`, `h4` `--text-lg`.
- `:focus-visible`: `outline: 3px solid var(--focus); outline-offset: 0; box-shadow: 0 0 0 6px var(--focus-halo);`
  (replaces the old 2px-offset ring).
- Links: `color: var(--link)`, `text-decoration-thickness: 1px`, `text-underline-offset: 0.18em`. On hover:
  `color: var(--link-hover)`, `text-decoration-thickness: 2px`.
- `.skip-link` uses `--surface`/`--link`. Keep `[hidden]`, `.visually-hidden`, `.num`, `.container`, `.page`, the
  reduced-motion block and `.icon`.

`templates/base.html`: `<meta name="theme-color" content="#1a3a6b">`.

- [ ] **Step 6: Build and run the tests**

```powershell
npm --prefix frontend run build
python -m uv run pytest tests/test_tokens.py apps/core -q
npm --prefix frontend run check; npm --prefix frontend run budget
```
Expected: the token/font tests PASS. Other component tests still pass, since markup is unchanged. Components look
partly unstyled where they used removed tokens; Tasks 2–4 fix that.

- [ ] **Step 7: Commit**

`git commit -m "feat: switch to civic palette, Lexend and Source Sans 3"` (stage the files listed above).

---

### Task 2: Controls and feedback

**Files:**
- Rewrite: `frontend/src/styles/components/buttons.css`, `forms.css`, `feedback.css`
- Modify: `templates/components/form_errors.html` (error summary), `templates/components/field.html` (only if the error
  bar needs a wrapper class), `apps/kit/templates/kit/sections/controls.html` and `feedback.html` (drop decorative
  icons from buttons)
- Test: `apps/core/tests/test_field_tag.py` (unchanged behaviour must pass); add `apps/kit/tests/test_restyle.py`

**Rules (exact):**

| Component | Rule |
|---|---|
| `.btn` | min-height `--control-height`; padding `0 var(--space-5)`; `border: 2px solid transparent`; radius `--radius-md`; font `600 var(--text-base)/1 var(--font-body)`; no shadow; transition background/border only |
| `.btn--primary` | bg `--primary`, text `--on-primary`; hover bg `--primary-hover` |
| `.btn--secondary` | bg `--surface`, border `--primary`, text `--primary`; hover bg `--primary-50` |
| `.btn--ghost` | transparent, text `--link`, underline; hover text `--link-hover`, thicker underline (no tinted bg) |
| `.btn--danger` | bg `--surface`, border `--danger`, text `--danger`; hover bg `--danger-50` |
| `.btn:disabled` | opacity .5, `cursor: not-allowed` |
| `.icon-btn` | 44×44, radius `--radius-md`, text `--text-muted`, hover bg `--surface-sunken` |
| `.field` | gap `--space-2`; label `600`; `.field__required` muted 400; help muted `--text-sm` |
| control | `border: 2px solid var(--border-control)`; radius `--radius-sm`; bg `--surface`; focus uses the global focus ring (no border colour swap) |
| `.field--invalid` | `padding-left: var(--space-4); border-left: 4px solid var(--danger)` on the field group; the control border is `--danger` (2px, so no layout shift); the message is `600`, `--danger`, placed above the control (already the order in field.html) with no icon |
| error summary (`form_errors.html`) | a `.banner .banner--danger` with `role="alert"`, title "There is a problem" (`.banner__title`), then the non-field errors as a list |
| `.banner` (rename of `.alert`; keep `.alert` as an alias selector until Task 5 removes uses) | `border-left: 5px solid`; bg tint; padding `--space-4 --space-5`; radius 0; title `600 var(--text-base)`; body `--text`; variants `--info` (navy bar, `--info-50`), `--success`, `--warning`, `--danger`; a leading icon is allowed only for warning and danger |
| `.toast` | the banner look on `--surface` with `--shadow-float`, 5px coloured left bar, radius `--radius-lg` |
| `.dialog` | radius `--radius-lg`; `--shadow-float`; header has a 1px bottom rule; title `--text-xl` Lexend |
| file input | `::file-selector-button` styled as `.btn--secondary` (2px navy border, navy text); progress bar 6px, radius 0, value `--primary` |
| spinner | 2px ring in currentColor (unchanged) |

- [ ] **Step 1: Write the failing test**

`apps/kit/tests/test_restyle.py`:
```python
import re

import pytest


@pytest.fixture
def kit_on(settings):
    settings.KIT_ENABLED = True


def test_buttons_carry_no_decorative_icons(client, kit_on, vite_build):
    body = client.get("/_kit/").content.decode()
    allowed = {"download", "x", "menu", "log-out"}
    for button in re.findall(r'<(?:a|button)[^>]*class="btn[^"]*"[^>]*>(.*?)</(?:a|button)>', body, re.S):
        assert set(re.findall(r"icons\.svg#([a-z0-9-]+)", button)) <= allowed, button


def test_form_errors_render_an_error_summary(client, kit_on, vite_build):
    body = client.get("/_kit/").content.decode()
    assert '<div class="banner banner--danger" role="alert">' in body
    assert "There is a problem" in body
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m uv run pytest apps/kit/tests/test_restyle.py -q`
Expected: FAIL. The trash-2, filter and banknote icons are present, and there is no banner.

- [ ] **Step 3: Implement** the rules table in the three CSS files and the template changes:
- `form_errors.html` becomes the error summary;
- remove the `trash-2` icon from "Withdraw application" and the `filter` icon from "Apply filters";
- remove `banknote` from "Release allowances" and `pencil` from "Complete your profile" wherever those sit inside a
  `.btn`.

Update `tests/e2e` selectors only if a class name they rely on changed. They use roles and text, so none should.

- [ ] **Step 4: Verify**: build, full `pytest -n auto`, the e2e suite, Biome (0 warnings), typecheck, budget. Run the
  mockup screenshot test with `MOCKUP_SCREENSHOTS` set to the scratchpad, open the kit controls/feedback states, and
  check that buttons, fields, errors and banners match the table.

- [ ] **Step 5: Commit**: `git commit -m "feat: restyle buttons, fields and feedback as flat civic components"`

---

### Task 3: Data display

**Files:**
- Rewrite: `frontend/src/styles/components/data.css`
- Modify: `templates/components/stat_tile.html` (it becomes the figure: no chip, no icon, no tone), `empty_state.html`
  (no icon), `tabs.html`, `breadcrumbs.html` (`›` separator)
- Modify: every template using `.pill` → `.tag` without the inner `{% icon %}`, and `.stat`/`.stats` → `.figure`/
  `.figures`. That covers `apps/kit/templates/kit/sections/*.html` and `apps/kit/templates/kit/mockups/*.html`, plus
  `apps/kit/samples.py` where a status dict carries an `icon` used only by tags (drop it).
- Test: append to `apps/kit/tests/test_restyle.py`; update any existing test asserting `class="stat ` or
  `pill pill--` markup to the new classes; add `tests/e2e/test_restyle.py`.

**Rules (exact):**

| Component | Rule |
|---|---|
| `.card` (panel) | bg `--surface`; `1px solid var(--border)`; radius `--radius-lg`; no shadow; padding `--space-6`; `.card__header` has `padding-bottom: var(--space-3); border-bottom: 1px solid var(--border); margin-bottom: var(--space-4)`; `.card__title` `600 var(--text-lg)` Lexend |
| `.figures` | `display: grid; grid-template-columns: repeat(auto-fit, minmax(12rem, 1fr))`; the row has a top `2px solid var(--border-strong)` rule and no background |
| `.figure` | padding `--space-4` 0; `border-left: 1px solid var(--border)` except the first in a row (`padding-left` `--space-5`); label `--text-sm` muted 600 (sentence case); value Lexend 600 `--text-2xl`, `tabular-nums`, `overflow-wrap: anywhere`; note `--text-sm` muted. Below 40rem the figures stack with a 1px top rule instead of the left rule |
| `stat_tile.html` → figure | `<div class="figure"><p class="figure__label">{{ label }}</p><p class="figure__value num">{{ value }}</p>{% if hint %}<p class="figure__note">{{ hint }}</p>{% endif %}</div>`; the `icon`/`tone` arguments are ignored (remove them from callers) |
| `.tag` | `display: inline-block`; padding `0.125rem var(--space-2)`; radius `--radius-sm`; `600 var(--text-sm)`; variants: `--success`/`--warning`/`--danger`/`--info` use the tint background + the status colour as text; default uses `--surface-sunken` + `--text` |
| `.table` | font `--text-base` (not small); header cells `600`, `--text`, bg none, `border-bottom: 2px solid var(--border-strong)`; body rows `1px solid var(--border)`; hover bg `--surface-sunken`; `.num` right and tabular; `.table-wrap` keeps overflow + focusable region, border `1px solid var(--border)`, radius `--radius-lg`, bg `--surface` |
| `.sort` | inherit colour; current column text `--text` with the arrow icon; others muted chevrons |
| `.tabs` | bottom `1px solid var(--border)`; links `--text-muted` 600; current `--text` with `box-shadow: inset 0 -4px 0 var(--primary)` (not a border, so no 1px overflow); count in a `.tag` |
| `.breadcrumbs` | `--text-sm`; separator `›` via `content: "›" / ""` |
| `.empty` | no icon, no dashed box: a `.card` with title `600 --text-lg`, body, one action |
| `.details` | keep the container query; `dt` muted `--text-sm` 600, `dd` `--text` |
| `meter`/`progress` | 8px tall, radius 0, track `--surface-sunken`, value `--primary` |
| `.steps` | numbered square markers (radius `--radius-sm`), current = navy fill white number, done = navy check; no green |
| `.timeline` | left 2px rule `--border`; event dot 8px square `--border-strong`; first `--primary` |
| `.bulk-bar` | bg `--primary-50`; left 5px `--primary` bar; count `600 --primary` |
| `.filters` | aligned to the bottom; inputs follow the field rules |
| `.checklist` | met = `check` icon in `--success`, unmet = `x` icon in `--danger`, pending = `info` icon in `--text-muted`; the text always carries the status word |

- [ ] **Step 1: Write the failing tests**

Append to `apps/kit/tests/test_restyle.py`:
```python
from apps.kit.views import MOCKUPS

KIT_PAGES = ["/_kit/"] + [f"/_kit/mockups/{slug}/" for slug in MOCKUPS]


@pytest.mark.parametrize("url", KIT_PAGES)
def test_tags_are_text_only(client, kit_on, vite_build, url):
    body = client.get(url).content.decode()
    tags = re.findall(r'<span class="tag[^"]*">(.*?)</span>', body, re.S)
    for tag in tags:
        assert "<svg" not in tag
        assert re.sub(r"<[^>]+>", "", tag).strip()
    assert 'class="pill' not in body


@pytest.mark.parametrize("url", KIT_PAGES)
def test_figures_have_no_icon_chips(client, kit_on, vite_build, url):
    body = client.get(url).content.decode()
    assert "stat__chip" not in body
    for figure in re.findall(r'<div class="figure">(.*?)</div>', body, re.S):
        assert "<svg" not in figure
```

`tests/e2e/test_restyle.py`:
```python
import pytest
from playwright.sync_api import Page

pytestmark = pytest.mark.e2e


def test_money_uses_tabular_figures(page: Page, live_server, vite_build):
    page.goto(f"{live_server.url}/_kit/mockups/disbursements/")
    for selector in (".figure__value", "td.num"):
        value = page.locator(selector).first.evaluate("(el) => getComputedStyle(el).fontVariantNumeric")
        assert "tabular-nums" in value, selector
```

- [ ] **Step 2: Run them to verify they fail** (pills and stat chips are still present).

- [ ] **Step 3: Implement** the rules table, the template and markup changes, and the class renames in the kit and
  mockups. Update the older tests that assert old class strings: `test_kit_shows_data_components` markers become
  `class="figure"` and `class="tag tag--`.

- [ ] **Step 4: Verify** with the same gate as Task 2, plus the screenshot review of the data section and all five
  mockups at 375 and 1440.

- [ ] **Step 5: Commit**: `git commit -m "feat: restyle data display with figures, tags and ruled tables"`

---

### Task 4: Layouts

**Files:**
- Rewrite: `frontend/src/styles/layouts.css`
- Modify: `templates/layouts/public.html`, `student.html`, `app.html`, `staff.html`, `office.html`, `auth.html`,
  `templates/components/nav_list.html` (no icons)
- Modify: `apps/kit/samples.py` (nav items lose their `icon` key; `NavItem` drops `icon`)
- Test: update `apps/core/tests/test_layouts.py` (NAV fixture without icons; new structure assertions); add to
  `tests/e2e/test_restyle.py`

**Rules (exact):**
- **Civic stripe:** every layout starts its `body` block with `<div class="civic-stripe" aria-hidden="true"></div>`.
  It is a 4px band: `background: linear-gradient(to right, var(--brand) 0 50%, var(--accent) 50% 100%)`. These are
  two flat halves, not a blend.
- **Brand block** (all layouts): `{% icon "logo" %}` in `--brand` on light surfaces and `--nav-text` (white) on navy, then "ScholarSync" in Lexend 600 `--text-lg` in
  `--text` (white on navy surfaces), then `<span class="brand__city">City of Taguig</span>` in `--text-sm` muted (nav
  muted on navy).
- **Public and student:**
  - White header, 1px bottom border `--border`, height ≥ 4rem.
  - Nav links are text-only, `--text` 600. The current item gets `box-shadow: inset 0 -4px 0 var(--primary)` and no
    background.
  - Student account area: the bell icon-btn with badge, then "Sign out" as `.btn--ghost`. The viewer name stays
    hidden at ≥64rem (existing rule).
  - Phone: the toggle stays as it is.
- **Staff and office (`app.html`):** replace the navy sidebar with:
  - a navy top bar (`<header class="appbar">`), height 3.5rem, holding:
    - the brand block (white);
    - for staff, the program switcher (white text, 1px `--nav-text-muted` border, radius `--radius-sm`) right after
      the brand;
    - on the right, the viewer name + role (muted) and the "Sign out" button (white text, transparent);
  - below it, a two-column shell: a white left nav (`<nav class="sidenav" aria-label="Main">`, width
    `--sidebar-width`, right border `1px solid var(--border)`, sticky, full height of the content) and the main column;
  - nav items are text-only, `--text` 600, min-height 44px. The current item gets bg `--primary-50`, text
    `--primary`, and `box-shadow: inset 4px 0 0 var(--primary)`. Counts use `.tag`;
  - the office has no switcher and shows "Scholarship office" as the area label in the top bar;
  - below 64rem the side nav collapses behind the existing menu toggle, which moves into the top bar
    (`aria-controls` points at the side nav id).
- **Auth:**
  - the split stays;
  - the panel is flat `--nav-bg` with the civic stripe on top, the brand block (white), the statement in Lexend 600
    `--text-3xl` white, and the note in nav muted;
  - no gold border rule.
- **Page header:** `h1`, then the meta line in muted. A 1px rule under the whole header (`padding-bottom: --space-4;
  border-bottom: 1px solid var(--border)`); actions sit on the right.
- **Remove** the `.shell` gradient, `.sidebar*` and the gold left border on auth.

- [ ] **Step 1: Write the failing tests**

In `apps/core/tests/test_layouts.py`:
- drop `"icon"` from the `NAV` dicts;
- change any assertion on the sidebar to the new structure;
- add:
```python
@pytest.mark.parametrize(
    "layout",
    ["layouts/public.html", "layouts/auth.html", "layouts/student.html", "layouts/staff.html", "layouts/office.html"],
)
def test_every_layout_has_the_civic_stripe(layout, vite_build):
    assert '<div class="civic-stripe" aria-hidden="true"></div>' in render(layout)


def test_app_shell_has_a_navy_top_bar_and_text_only_side_nav(vite_build):
    html = render("layouts/staff.html")
    assert '<header class="appbar">' in html
    nav = html[html.index('<nav class="sidenav"'):]
    nav = nav[: nav.index("</nav>")]
    assert "<svg" not in nav
    assert 'aria-current="page"' in nav
```
Append to `tests/e2e/test_restyle.py`:
```python
def test_focus_is_visible_on_the_navy_top_bar(page: Page, live_server, vite_build):
    page.set_viewport_size({"width": 1280, "height": 800})
    page.goto(f"{live_server.url}/_kit/layouts/staff/")
    page.keyboard.press("Tab")  # skip link
    page.keyboard.press("Tab")  # brand link in the top bar
    focused = page.evaluate(
        "() => { const s = getComputedStyle(document.activeElement);"
        " return [document.activeElement.closest('.appbar') !== null, s.outlineStyle, s.boxShadow]; }"
    )
    assert focused[0] is True
    assert focused[1] != "none"
    assert focused[2] != "none"
```

- [ ] **Step 2: Run them to verify they fail.**

- [ ] **Step 3: Implement** the layout rules.

- [ ] **Step 4: Verify** with the same gate, including every existing layout e2e test (phone overflow, toggle, no-JS
  nav, sidebar open on desktop: update that test's name and selector to the side nav if needed, keeping its intent).
  Review screenshots of all five layouts at 375 and 1280.

- [ ] **Step 5: Commit**: `git commit -m "feat: restyle layouts with civic stripe, app bar and text nav"`

---

### Task 5: Mockups and kit content pass

**Files:**
- Modify: `apps/kit/templates/kit/mockups/*.html`, `apps/kit/templates/kit/sections/*.html`, `apps/kit/samples.py`,
  `frontend/src/styles/kit.css` (swatches for the new palette: update `SWATCHES` in `apps/kit/views.py` to the new
  palette names)
- Test: existing mockup tests; `test_every_swatch_is_a_token_with_a_kit_style` (with the new swatch list)

**Rules:**
- **No nested boxes.** A mockup page is a page header, an optional `.figures` row, then panels in `.split`. Inside a
  panel, use `.details`, tables and lists, never another `.card`.
- **One primary action per screen region.** The others are secondary or ghost. Danger actions are outlined.
- **Remove leftover decorative icons:** checklist icons stay (they carry meaning with text); download links keep the
  download icon.
- **Copy:** sentence case, plain verbs, no middle-dot meta strings. Replace any "A · B" with a comma or two lines.
- **Swatches:** `SWATCHES = ["ink-900", "ink-600", "stone-50", "stone-100", "stone-300", "stone-600", "white",
  "navy-700", "navy-800", "navy-50", "navy-muted", "red-700", "red-50", "gold-400", "green-800", "green-50",
  "amber-800", "amber-50"]`, with matching `.kit-swatch--<name>` rules in `kit.css`. Remove the old ones.
- **Alias removal:** remove the `.alert` alias selectors added in Task 2 once no template uses `.alert`. Grep
  `class="alert` must find nothing.

- [ ] **Step 1:** Update `SWATCHES` and run `apps/kit/tests/test_kit.py::test_every_swatch_is_a_token_with_a_kit_style`.
  It fails until `kit.css` matches.
- [ ] **Step 2:** Update `kit.css` and the templates and samples per the rules.
- [ ] **Step 3: Verify** with the full gate (ruff, format, mypy, makemigrations, deploy check, `pytest -n auto`, e2e,
  typecheck, Biome with 0 warnings, budget, pip-audit). Then regenerate the screenshots at phone, laptop and desktop
  (`MOCKUP_SCREENSHOTS`) and walk UI UX Pro Max's pre-delivery checklist against them:
  - no emoji icons;
  - pointer cursor on clickables;
  - 150–300 ms hover transitions;
  - 4.5:1 text;
  - visible focus;
  - reduced motion;
  - works at 375/768/1024/1440.

  Record the result in the report.
- [ ] **Step 4: Commit**: `git commit -m "feat: rework mockups and kit content for the civic redesign"`

---

## Finish
- Whole-branch review of this plan's range on the most capable model. Give it the spec §12 rev 3 and the anti-pattern
  list, and have it look at the screenshots and judge whether anything still reads as templated.
- One fix wave if needed, then a scoped re-review.
- Then the M3 gate again: Kenneth reviews `/_kit/mockups/` and the new screenshots.
