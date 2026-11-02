# M3c Redesign Implementation Plan

**Goal:** Restyle the whole front end to spec §12 revision 4 so that the design kit and every mockup match Kenneth's
canvas: red primary, blue secondary, yellow accent, a white sidebar shell, cards, one figures box, and status as
coloured text.

**Architecture:** This is a restyle of the existing token, component and layout system; no new front-end framework.
- Tokens change in `tokens.css`.
- Components keep their class names where the role is unchanged (`.btn`, `.card`, `.figures`, `.tabs`, `.table`,
  `.banner`).
- The status tag becomes `.status` text and counts become `.count` pills.
- `staff`, `office` and `student` share one new sidebar shell in `layouts/app.html`.
- The drawer is server-rendered, so there is no new TypeScript beyond `nav.ts` changes.

**Tech Stack:** Django templates, plain CSS tokens (Vite build), Lucide sprite (`frontend/src/icons/icons.json`),
pytest and Playwright.

**Spec:** `docs/superpowers/specs/2026-10-11-scholarsync-v2-design.md` §12 (revision 4). The visual reference is the
canvas boards in `docs/design/2026-10-30-redesign/`: `Main.dc.html` (Scholars), `Office.dc.html`, `Review.dc.html`,
`Student.dc.html` and `Palette.dc.html`. Open them in a browser to read exact sizes, spacing and copy. Their inline
styles are the reference values. Translate them into tokens and classes; never copy inline styles into templates (the
CSP forbids them).

## Global Constraints

- Every colour, size and radius comes from a token in `tokens.css`. No raw hex in component or layout CSS.
- WCAG 2.2 AA. Every text pair the components use is listed in `tests/test_tokens.py` and reaches 4.5:1. Yellow
  `#f2b705` is never text on a light background (its `color:` use is banned, as gold is today).
- No inline `style=`, no inline scripts, no `hx-on`. `{% icon %}` names must exist in `icons.json`, or the build fails.
- No middle dot `·` anywhere in a page body; the existing rule stays. Where the canvas uses "·", write a colon, comma or
  parentheses ("Overdue: window closes 15 November", "5 of 8 passed (63%)").
- Copy from the canvas, with Kenneth's rulings (spec §12 rev 4):
  - no subtitle under the Office heading;
  - status as coloured text;
  - tiers as plain text;
  - no timeline dots;
  - no step pills;
  - no icons in the figures box.
- Sample data stays Faker-only (`apps/kit/samples.py`), never real people.
- One Conventional Commit per task, staging only that task's files. 
- Never push.
- Python edits from scripts use `encoding="utf-8"` and `newline="\n"`.
- The full gate after each task: `python -m uv run pytest -n auto`, the e2e suite, `ruff check .`,
  `ruff format --check .`, `mypy .`, and `npm --prefix frontend run typecheck|check|build|budget`. The budget is
  ≤ 100 KB gzipped.

## Review Focus

1. **Phone width (375 px).** Expected:
   - the sidebar collapses behind the menu button;
   - the top bar wraps;
   - the figures box cells wrap;
   - tables scroll inside their box;
   - the drawer becomes full width;
   - nothing scrolls sideways.

   Covered by the e2e `test_mockup_fits_and_has_no_errors` (kept, now including the new Scholars mockup) and by Task 7's
   drawer test.
2. **Keyboard only.** Every sidebar link, the program switcher, the term chooser, the account menu and the drawer's
   close link are reachable. Each shows the ink outline with the yellow halo, on white, on the red-tint current nav
   item and on the red auth panel. Task 3 pins the focus style on the current nav item; Task 4 pins it on the red auth
   panel.
3. **Long names and big numbers.** A long program name in the switcher, "₱18,240,000.00" in a figure cell and a
   40-character scholar name in the table must wrap or truncate, never overflow. Kept: the e2e tests
   `test_stat_values_stay_inside_their_tiles` and `test_money_figures_never_break_mid_number`; Task 7 adds a long
   sample name.
4. **No JavaScript.** The navigation is visible on a phone, the drawer opens and closes through links, and the chart's
   table is reachable. Kept: e2e `test_nav_is_visible_without_javascript_on_a_phone`; Task 7 adds a JS-off drawer
   test.
5. **Status is never colour alone.** Every status reads as a word ("At risk", "Overdue: …"), so colour-blind users
   lose nothing. Task 2 adds a unit test: every `.status` element has non-empty text.

---

### Task 1: Tokens, base type and the kit colour section

**Files:**
- Modify: `frontend/src/styles/tokens.css`, `frontend/src/styles/base.css`, `frontend/src/styles/kit.css` (swatch
  classes), `apps/kit/templates/kit/sections/colour.html`, `apps/kit/templates/kit/sections/type.html`,
  `templates/base.html` (`theme-color` becomes `#b8132a`)
- Test: `tests/test_tokens.py`, `apps/kit/tests/test_kit.py`

**Interfaces:**
- **Palette primitives:** `--red-700 #b8132a`, `--red-800 #9b1022`, `--red-50 #fbe7ea`, `--blue-700 #1f4e9e`,
  `--blue-800 #163a78`, `--blue-50 #e4ebf6`, `--yellow-500 #f2b705`, `--yellow-50 #fef8e1`, `--yellow-100 #fcefc4`,
  `--gold-700 #8f6500`, `--green-800 #11663a`, `--ink-900 #0e1b2c`, `--slate-700 #3d4654`, `--slate-500 #5b6472`,
  `--slate-300 #d0d5dd`, `--slate-200 #e4e7ec`, `--slate-150 #eef0f3`, `--slate-100 #f1f2f5`, `--slate-50 #f5f6f8`,
  `--slate-25 #fafafb`, `--white`.
- **Roles:**

  | Role | Value |
  |---|---|
  | `--text` | ink |
  | `--text-secondary` | slate-700 |
  | `--text-muted` | slate-500 |
  | `--bg` | slate-50 |
  | `--surface` | white |
  | `--surface-hover` | slate-100 |
  | `--surface-header` | slate-25 |
  | `--track` | slate-150 |
  | `--border` | slate-200 |
  | `--border-control` | slate-300 |
  | `--primary` | red-700 |
  | `--primary-hover` | red-800 |
  | `--primary-50` | red-50 |
  | `--on-primary` | white |
  | `--secondary` | blue-700 |
  | `--secondary-hover` | blue-800 |
  | `--secondary-50` | blue-50 |
  | `--link` | blue-700 |
  | `--link-hover` | blue-800 |
  | `--accent` | yellow-500 |
  | `--accent-50` | yellow-50 |
  | `--accent-100` | yellow-100 |
  | `--on-accent` | ink |
  | `--brand` | red-700 |
  | `--danger` | red-800 |
  | `--danger-50` | `#fdecee` |
  | `--success` | green-800 |
  | `--success-50` | `#e7f3ec` |
  | `--warning` | gold-700 |
  | `--warning-50` | yellow-50 |
  | `--info` | blue-700 |
  | `--info-50` | blue-50 |
  | `--focus` | ink |
  | `--focus-halo` | yellow-500 |
  | `--focus-ring` | `0 0 0 6px var(--focus-halo)` |

- **Navigation:** `--nav-bg` white, `--nav-text` slate-700, `--nav-current` primary, `--nav-current-bg` primary-50,
  `--nav-count-bg` accent.
- **Type:** `--text-base: 1rem` (16 px), `--text-sm: 0.875rem`, `--text-xs: 0.8125rem` (13 px),
  `--leading-body: 1.5`. The heading scale stays.
- **Shape:** `--radius-sm: 8px`, `--radius-md: 10px`, `--radius-lg: 12px`, `--radius-pill: 999px`.
- **Size:** `--sidebar-width: 15.5rem` (248 px).
- **Removed:** every navy, stone, amber and `--gold-400` token, and `--nav-marker`. Every former use is migrated in
  Tasks 2–4. In Task 1, `layouts.css` and the component CSS may still reference removed names only through aliases
  defined at the bottom of `tokens.css` under `/* M3c migration aliases: removed in Task 4 */`.

- [ ] **Step 1: Write the failing tests.**
  - Rewrite `TEXT_PAIRS` in `tests/test_tokens.py` for the new roles, with each value from the spec:
    - text, text-secondary and text-muted on surface, bg and surface-header;
    - link on surface and bg;
    - on-primary on primary and primary-hover;
    - primary on primary-50;
    - danger on surface and danger-50;
    - success on surface and success-50;
    - warning on surface and warning-50;
    - info on surface and info-50;
    - secondary on secondary-50;
    - on-accent on accent;
    - nav-text and nav-current on nav-bg;
    - nav-current on nav-current-bg;
    - on-primary on brand.
  - `NON_TEXT_PAIRS`: border-control on surface (3:1 is not required for a border with a visible label, so drop it
    if it fails and note why in a comment); focus on surface, bg and primary-50; primary on surface.
  - `DECORATIVE_AS_TEXT` bans `color: var(--(accent|yellow-500|focus-halo|nav-count-bg))`.
  - Add `test_text_pairs_include_the_status_tones`, asserting the five status tones are present in `TEXT_PAIRS`.
- [ ] **Step 2: Run them.** `python -m uv run pytest tests/test_tokens.py -q`. Expected: FAIL (unknown tokens).
- [ ] **Step 3: Implement the tokens and base.** Update `base.css` for the body size and line height, and give
  headings Lexend 600; set `--text-3xl` to 1.75rem (h1 is 28 px on the canvas). Update the kit swatches so
  that `test_every_swatch_is_a_token_with_a_kit_style` passes, and update the type section's copy (16 px body,
  13 px captions).
- [ ] **Step 4: Run the full gate.** The visual e2e tests that check old navy or gold values
  (`test_current_tab_keeps_the_focus_halo` expects `rgb(240, 179, 35)`) now expect `rgb(242, 183, 5)`. Update that
  assertion.
- [ ] **Step 5: Commit.** `git commit -m "feat: red, blue and yellow design tokens"`

### Task 2: Components

**Files:**
- Modify:
  - `frontend/src/styles/base.css`, or `components.css` if component rules live there (follow the existing split;
    create `frontend/src/styles/components.css` and import it from `main.ts` only if components currently sit in
    `layouts.css`);
  - `templates/components/{stat_tile,tabs,nav_list,pagination,empty_state}.html`;
  - `apps/core/templatetags/ui.py`;
  - `apps/kit/templates/kit/sections/{controls,data,feedback,overlays}.html`;
  - `frontend/src/icons/icons.json`.
- Create:
  - `templates/components/{status,avatar,figures,row_links,drawer,progress}.html`;
  - `apps/kit/templates/kit/sections/components.html`, only if the existing sections can't host the new pieces.
- Test: `apps/kit/tests/test_restyle.py` (rewritten), `apps/core/tests/test_ui_tags.py`,
  `apps/core/tests/test_layouts.py` (the nav count assertion)

**Interfaces (classes and template tags later tasks use):**
- **Buttons:** `.btn` plus one of `--primary`, `--secondary`, `--soft`, `--ghost` or `--danger`. Radius 8, 44 px tall,
  weight 600.
- **Cards:** `.card`, `.card__header` (title on the left and an optional link), `.card__title`. Radius 12, border
  `--border`, padding 20/24 px. Sections inside pages use `.card`; the old `.section` and `.panel` classes are deleted.
- **Figures:** `.figures` (a bordered box, 1 px gaps on `--border`) containing `.figure` cells, each with
  `.figure__label` and `.figure__value` (Lexend 28 px, `num`). `stat_tile.html` keeps its name and context
  (`label`, `value`) and drops `hint`: Kenneth ruled no captions.
- **Status:** `{% status tone text %}`, a new simple tag in `ui.py`. It renders
  `<span class="status status--{tone}">{text}</span>`; tone ∈ {success, warning, info, danger, neutral}. Any other tone
  raises `TemplateSyntaxError`.
- **Counts:** `.count` (a pill), with `.count--accent` for the nav count (yellow, ink text) and `.count--current` for
  the current tab (red tint, red text). `nav_list.html` and `tabs.html` render counts with these. `.tag` is deleted
  everywhere.
- **Avatars:** `{% avatar name index %}`, a new tag. It renders `<span class="avatar avatar--{red|blue|yellow}"
  aria-hidden="true">{initials}</span>`, cycling red, blue and yellow by `index % 3`, with initials from the first and
  last word. It takes a size modifier: `{% avatar name index size="lg" %}` adds `avatar--lg` (64 px).
- **Tabs:** `.tabs`, with links having a 3 px bottom border; the current one has a `--primary` border and `--text`
  colour.
- **Table:** `.table` header cells on `--surface-header`, `--text-xs` bold `--text-muted`; row hover `--surface-hover`;
  `.table-toolbar` (a flex-wrap row for search, selects and buttons).
- **Pagination:** `pagination.html` becomes numbered. It uses `page.paginator.get_elided_page_range(page.number,
  on_each_side=1, on_ends=1)`, with the current page a red `btn` and `aria-current="page"`, and keeps the
  `id="page-prev"` and `id="page-next"` that the e2e table tests use. The status text "Page X of Y" becomes visually
  hidden.
- **Progress:** a `<progress class="progress progress--{primary|secondary|success}" max value>` element: 8 px track
  `--track`, radius pill, the fill coloured by the modifier through `::-webkit-progress-value` and
  `::-moz-progress-bar`. It is a real element, not a div with an inline width, because the CSP forbids inline styles.
- **Row links:** `row_links.html` takes `items` (each with `title`, `detail`, `tone`, `url`) and renders
  `<ul class="row-links">` of `<a class="row-link">` containing the title, a `.status--{tone}` detail line and an
  `arrow-right` icon.
- **Drawer:** `drawer.html` takes `drawer_id`, `title` and `close_url`, and renders `<aside class="drawer"
  id="{drawer_id}" tabindex="-1" aria-labelledby="{drawer_id}-title">`, with a header (a small title and a close
  `<a class="icon-btn" href="{close_url}" aria-label="Close details">`) and a body block filled by an `{% include …
  with %}` partial or `{% block %}`. CSS:
  - from 64rem: fixed to the right, 400 px wide, full height, left border and the shadow token, scrolling inside;
  - below 64rem: full width.
- **Banners:** `.banner` keeps its modifiers. The look becomes a tinted background, a 1 px border in the tone's
  100-level colour and radius 12. Warning and danger keep an icon, info has none (the existing rule).
- **New Lucide icons** in `icons.json`:
  - `layout-dashboard`, `file-text`, `users`, `banknote`, `calendar`, `chart-column`, `sliders-horizontal`;
  - `circle-help`, `search`, `bell`, `plus`, `filter`, `ellipsis`, `ellipsis-vertical`, `mail`;
  - `chevron-left`, `chevron-right`, `arrow-right`, `house`, `building-2`, `shield`, `triangle-alert`, `clock`,
    `circle-pause`, `log-out`.

  Keep whichever of these already exist; the build fails on a misspelt name.

- [ ] **Step 1: Write the failing tests.**
  - **`apps/kit/tests/test_restyle.py`:** rewrite it around rev 4, keeping the HTML-parser helpers.
    - Keep:
      - `test_form_errors_render_an_error_summary`;
      - `test_no_card_sits_inside_another_card`;
      - the no-middle-dot half of `test_pages_use_banners_and_plain_meta`;
      - `test_only_warning_and_danger_banners_carry_an_icon`;
      - `test_file_input_error_sits_above_the_control_without_an_icon`.
    - `test_buttons_carry_no_decorative_icons`: the allowed set becomes `{"download", "x", "menu", "log-out", "plus",
      "mail", "circle-pause", "chevron-left", "chevron-right", "filter"}`.
    - `test_status_is_coloured_text_not_a_tag` (every kit page): no `class="tag`; every `<span class="status
      status--…">` has non-empty text and no `<svg`; tones ⊆ {success, warning, info, danger, neutral}.
    - `test_figures_box_has_no_icons_or_notes` (every page): no `<svg` inside `.figures` and no `figure__note`.
    - `test_kit_copy_describes_the_redesign`: the kit index mentions "Lexend", "Source Sans 3", "Figures" and
      "red", and does not contain "navy" or "Swiss".
    - Delete `test_tags_are_text_only`, `test_tags_use_only_defined_tones`,
      `test_secondary_regions_are_sections_not_panels`, `test_review_status_sits_on_the_meta_line`,
      `test_kit_shows_an_unboxed_section` and the old figures test; rev 4 overturns them.
  - **`apps/core/tests/test_ui_tags.py`:**
    - `test_status_renders_tone_and_text`;
    - `test_status_rejects_unknown_tones`;
    - `test_status_escapes_text`;
    - `test_avatar_initials_and_tone_cycle`: `("Daniel Montoya", 0)` → `DM`, `avatar--red`; index 1 → `avatar--blue`;
      index 2 → `avatar--yellow`; index 3 → `avatar--red`;
    - `test_avatar_single_word_name`: `"Cher"` → `C`.
  - **`apps/core/tests/test_layouts.py::test_current_nav_item_is_marked`:** expect
    `<span class="count count--accent">2</span>` instead of the old tag.
- [ ] **Step 2: Run them.** `python -m uv run pytest apps/kit apps/core -q`. Expected: FAIL.
- [ ] **Step 3: Implement** the CSS, component templates and tags. Update the kit sections so every component shows
  every state: buttons ×5 plus disabled; status ×5; counts; avatars ×3 plus lg; figures; tabs; table with toolbar,
  hover and numbered pagination; progress ×3; row links ×3 tones; drawer (rendered inline in a kit frame, not
  fixed); banners ×4; dialog; toast; empty state.
- [ ] **Step 4: Run the full gate.** The mockups still render with the old markup until Tasks 5–7; fix only what
  breaks the build or the suite (for example a deleted `.tag` class used by a mockup becomes `{% status %}` now).
- [ ] **Step 5: Commit.** `git commit -m "feat: restyle components for the redesign"`

### Task 3: The sidebar app shell (staff, office, student)

**Files:**
- Modify:
  - `templates/layouts/{app,staff,office,student}.html`;
  - `frontend/src/styles/layouts.css`;
  - `frontend/src/nav.ts`, only if the toggle needs a new target;
  - `templates/components/nav_list.html`;
  - `apps/kit/samples.py` (`chrome()` and the `*_NAV` lists).
- Test:
  - `apps/core/tests/test_layouts.py`;
  - `tests/e2e/test_layouts.py`, `tests/e2e/test_restyle.py`.

**Interfaces:**
- **Layout context:**
  - `nav_items`: each item gains `icon: str`;
  - `nav_secondary`: optional, same shape, rendered under a "Support" heading;
  - `nav_heading`: default "Workspace";
  - `viewer` (`name`, `role`);
  - `logout_url`;
  - `search_url`: optional; staff and office get a search form when set;
  - `terms`: optional list of `{name, url, current}` for the term chooser;
  - `notifications_url` and `notifications_count`.
- **Blocks:**
  - `sidebar_context`: staff = program switcher, office = the "Scholarship office" block, student = empty;
  - `sidebar_callout`: empty by default; the staff Scholars mockup fills it with the renewal callout;
  - `topbar_extra`.
- **Structure** of `layouts/app.html`: `<div class="app">`, holding:
  1. `<nav class="sidebar" id="app-nav" aria-label="Main">`, with:
     - `.civic-stripe` (three bands: red 2fr, blue 1fr, yellow 1fr);
     - `.brand` (logo in a red 40 px rounded square, wordmark, "City of Taguig");
     - `{% block sidebar_context %}`;
     - the nav groups, each with a group heading `.sidebar__heading` and `nav_list` with icons;
     - a spacer;
     - `{% block sidebar_callout %}`;
     - `.sidebar__user`, a `<details class="account-menu">` whose summary shows the avatar, name and role, and whose
       menu holds the sign-out POST form.
  2. `<div class="app__main">`, holding:
     - `<header class="topbar">`: the menu toggle (`data-nav-toggle`, `hidden` until JS), the search form when
       `search_url`, then on the right the term chooser `<details class="switcher">` when `terms` and the
       notifications link with an unread dot;
     - `<main id="main" class="page">`, holding the breadcrumbs and content.
- **`student.html`** extends `app.html`, with no search and no context block. Its nav is Home, Find programs,
  Applications (count), Allowances, Profile, plus "Help and guides" under Support.
- **Current nav item:** `--nav-current-bg` background and `--nav-current` text and icon colour. Focus shows the ink
  outline and yellow halo.
- **Below 64rem:** the sidebar is collapsible (`nav.ts` `is-collapsible` / `is-open`, as today); the top bar shows the
  menu button; the sidebar opens above the content at full width.

- [ ] **Step 1: Write the failing tests.**
  - **`apps/core/tests/test_layouts.py`:**
    - keep `test_every_layout_has_one_main_a_skip_link_and_the_logo`, the nav-toggle test, the switcher test and the
      sign-out POST test;
    - `test_every_layout_has_the_civic_stripe` now expects `class="civic-stripe"` inside `.sidebar` for staff, office
      and student, and at the top for public and auth;
    - replace the navy app-bar tests with `test_app_shell_has_a_sidebar_and_a_topbar`: for staff, office and student,
      there is exactly one `<nav class="sidebar"`, one `<header class="topbar">` and one `<main id="main"`, and the
      sidebar contains `icons.svg#` for every nav item;
    - `test_staff_topbar_has_search_only_with_a_search_url`;
    - `test_office_sidebar_shows_the_office_context`;
    - `test_account_menu_holds_sign_out` (a POST form inside `details.account-menu`).
  - **`tests/e2e/test_layouts.py`:**
    - keep the phone-fit, nav-toggle, desktop-open and no-JS tests, retargeted to `.sidebar`;
    - replace `test_student_top_bar_is_one_row_from_64rem` with `test_sidebar_is_248px_on_desktop` (staff, office and
      student at 1280 px: the sidebar width is 248 px).
  - **`tests/e2e/test_restyle.py`:**
    - replace `test_focus_is_visible_on_the_navy_top_bar` with
      `test_focus_is_visible_on_the_current_nav_item`: Tab to the current sidebar link; outline style is not `none`,
      and the box-shadow contains `rgb(242, 183, 5)`;
    - keep `test_short_app_page_does_not_scroll` (staff layout at 1280×800).
- [ ] **Step 2: Run them.** `python -m uv run pytest apps/core/tests/test_layouts.py -q` and the e2e layout tests.
  Expected: FAIL.
- [ ] **Step 3: Implement** the layouts, CSS and `samples.chrome()` (icons per nav item; staff gets `search_url="#"`
  and `terms` for "1st sem 2026–2027"). Delete the `.appbar`, `.sidenav` and `.topnav` rules that no layout uses any
  more, and remove Task 1's migration aliases.
- [ ] **Step 4: Run the full gate.**
- [ ] **Step 5: Commit.** `git commit -m "feat: white sidebar shell for staff, office and student"`

### Task 4: Public and auth layouts

**Files:**
- Modify: `templates/layouts/{public,auth}.html`, `frontend/src/styles/layouts.css`
- Test: `apps/core/tests/test_layouts.py`, `tests/e2e/test_restyle.py`, `tests/e2e/test_layouts.py`

**Interfaces:**
- **Public:** the stripe on top; a white `.topbar` with the brand on the left and text nav on the right, where the
  current item has a 3 px red underline; content max 72rem; the footer unchanged in this task (M3.5 Task 9 replaces
  it).
- **Auth:** the stripe on top; `.auth__panel` on `--primary` with `--on-primary` text. The brand's logo square turns
  white with a red cap so it shows on red. The tagline is Lexend, the note is white at full opacity: the old
  muted-on-navy colour fails on red, so use `--on-primary` for both.

- [ ] **Step 1: Write the failing tests.**
  - `test_auth_panel_uses_on_primary_text` (in `test_layouts.py`): the auth layout's CSS rules for `.auth__panel`
    reference `--on-primary` and never `--text-muted` (white on red is already in `TEXT_PAIRS`).
  - e2e `test_focus_is_visible_on_the_red_auth_panel`: Tab to the panel's brand link; the outline is ink and the halo
    yellow.
  - Keep `test_auth_form_starts_near_the_top_on_a_phone` and `test_logo_sits_beside_the_name`.
- [ ] **Step 2: Run them**, expecting FAIL; then **implement**.
- [ ] **Step 3: Run the full gate.**
- [ ] **Step 4: Commit.** `git commit -m "feat: restyle public and auth layouts"`

### Task 5: Office overview mockup

Reference: `docs/design/2026-10-30-redesign/Office.dc.html`.

**Files:**
- Modify: `apps/kit/templates/kit/mockups/office_dashboard.html`, `apps/kit/samples.py` (`office_dashboard()`),
  `frontend/src/styles/layouts.css` or the component CSS (`.bar-chart`)
- Test: `apps/kit/tests/test_mockups.py`, `tests/e2e/test_mockups.py`

**Interfaces:**
- **`office_dashboard()` context:**
  - `greeting = "Good morning, Jessica"`;
  - `figures`: a list of `{label, value}`: Scholars 1,284; Applications 645; Waiting over 7 days 12; Reports to
    review 3;
  - `months`: each `{label, short, count, percent, current}`, with percent relative to 250 and October current;
  - `attention`: row-link items with tones: reports `warning` "Oldest sent 4 days ago"; LANI `danger`
    "Overdue: window closes 15 November"; budget `warning` "2 months left in the school year";
  - `programs`: as today, plus `initials_index`;
  - `activity`: as today.
- **The page:**
  - header: the h1 greeting with no subtitle, and the actions "Download report" (secondary, download icon) and
    "New program" (primary, plus icon);
  - the figures box;
  - a row: "Applications by month" card (2fr) and "Needs attention" card (1fr);
  - a row: "Programs" card (table with avatar initials, name link, window line, numbers and a budget `progress`) and
    "Recent activity" card (plain list: text and time, no dots).
- **The chart** is server-rendered `.bar-chart`: one `<li>` per month with a bar whose height comes from a
  `data-percent` attribute, mapped by CSS attribute selectors in 5 % steps (`[data-percent="65"]` etc.; the CSP
  forbids inline heights). Bars are blue; the current month is red. The value label shows on the current month.
  Under it, `<details><summary>View as table</summary>` holds the accessible table. The chart `<ul>` is
  `aria-hidden="true"`, so the table is the accessible source.

- [ ] **Step 1: Write the failing tests** in `apps/kit/tests/test_mockups.py`:
  - `test_office_overview_has_no_subtitle`: no `page-header__meta` on the page;
  - `test_office_figures_are_label_and_value_only`;
  - `test_attention_rows_are_links_with_severity`: three `a.row-link`, each with an `arrow-right` icon; the LANI row
    has `status--danger`, the others `status--warning`;
  - `test_activity_has_no_dots`: no `timeline__dot` and no `<svg` inside the activity list;
  - `test_chart_has_a_table_fallback`: a `<details>` containing a `<table>` with the five months, and a chart with
    `aria-hidden="true"`;
  - `test_chart_percent_steps_are_multiples_of_five`.
- [ ] **Step 2: Run them**, expecting FAIL; then **implement**.
- [ ] **Step 3: Compare with the canvas at 1440 px and 375 px.** Take a screenshot of `/_kit/mockups/office-dashboard/`
  and the canvas board, and save them to the session scratchpad. Fix visible differences, except the hover readout
  (dropped: no JS) and the chart/table toggle (replaced by `<details>`).
- [ ] **Step 4: Run the full gate.**
- [ ] **Step 5: Commit.** `git commit -m "feat: restyle the office overview mockup"`

### Task 6: Application review and student mockups

References: `docs/design/2026-10-30-redesign/Review.dc.html` and `Student.dc.html`.

**Files:**
- Modify: `apps/kit/templates/kit/mockups/{application_review,student_dashboard}.html`, `apps/kit/samples.py`
- Test: `apps/kit/tests/test_mockups.py`

**Interfaces:**
- **Review page:**
  - a header card: large avatar, h1 name, "Under review" status, a meta line without status, a prev/next pager in the
    top bar block, the "Review checks" progress (`progress--secondary`, "5 of 8 passed (63%)"), then the tabs;
  - left column:
    - "Applicant" card (a `dl` grid);
    - "Documents" card: a table with status text and a 2 of 4 `progress--success`. The waiting row's actions are
      Download, Approve (primary) and Decline (danger);
    - "Eligibility" card: the rules list with check and alert icons (these stay: they carry meaning); "Not met" in
      warning text; the legacy-model note as an info banner.
  - right column:
    - "Decision" card: a radio fieldset (Approve / Return to applicant / Reject), the note field, and a submit button
      that is primary, or danger when Reject is selected. Without JS it stays primary, with the copy "Submit
      decision". The canvas's live label change is a progressive enhancement: skip it, there is no new TS;
    - "History" card: plain list, no dots.
- **`samples.application_review()`** gains `checks = {"passed": 5, "total": 8, "percent": 63}`.
- **Student page:**
  - h1 "Your scholarships" with its meta line kept (Kenneth didn't rule on this one);
  - the warning banner "LANI returned your application…" with the "Fix application" button;
  - the red award card (`.award-card`: "Active" in white text, tier, allowance, "Next release" in yellow Lexend 20 px
    bold, the renew note);
  - "Your profile" card with `progress--secondary`;
  - "Applications" and "Allowances" tables with status text;
  - "Notifications" card as a plain list.

- [ ] **Step 1: Write the failing tests:**
  - `test_review_has_a_checks_progress_and_no_step_pills`: `<progress class="progress progress--secondary" max="8"
    value="5"` present; no `steps` class;
  - `test_review_decision_is_a_radio_group`;
  - `test_review_history_has_no_dots`;
  - `test_student_award_card_status_is_text`: "Active" with no `status` pill;
  - `test_student_next_release_is_large_yellow_text`: `.award-card__release` present;
  - `test_student_dashboard_has_a_service_title`: kept (h1 and meta with "Carolyn Hawkins").
- [ ] **Step 2: Run them**, expecting FAIL; **implement**; then **compare with the canvas** at 1440 px and 375 px, as in
  Task 5 step 3.
- [ ] **Step 3: Run the full gate.**
- [ ] **Step 4: Commit.** `git commit -m "feat: restyle the review and student mockups"`

### Task 7: Scholars mockup with the drawer; disbursements and apply

Reference: `docs/design/2026-10-30-redesign/Main.dc.html`.

**Files:**
- Modify:
  - `apps/kit/views.py` (register `scholars` in `MOCKUPS`; the view reads `?status=` and `?scholar=`);
  - `apps/kit/samples.py` (a `scholars_page(status: str, scholar: int | None) -> dict` that reuses `scholars()` and
    adds email, course, barangay, since, gwa, avatar index and the drawer data; at least one 40-character name);
  - `apps/kit/templates/kit/mockups/{disbursements,apply}.html`.
- Create: `apps/kit/templates/kit/mockups/scholars.html`
- Test: `apps/kit/tests/test_mockups.py`, `tests/e2e/test_mockups.py`

**Interfaces:**
- **Scholars page:**
  - the figures box: Active scholars 900, At risk 37, On hold 12, Budget used 64%;
  - a card holding the status tabs, as links `?status=all|active|at_risk|on_hold|ended` with counts 968, 900, 37, 12
    and 19;
  - the toolbar: search, school and tier selects, "More filters", and "Sorted by name, A to Z";
  - the table: checkbox, avatar, name link `?status=…&scholar=<id>#scholar-drawer`, email, school, tier as plain
    text, allowance, GWA (danger text below 80), status text, row menu;
  - numbered pagination.
- **The drawer** renders when `scholar` is valid:
  - avatar lg, name, status and tier as text, "Email" (secondary) and "Open record" (primary);
  - the details list;
  - the "Renewal check" box: a progress of the GWA, an 80 % marker drawn as a CSS pseudo-element, and the note;
  - "Allowances": three rows with status text;
  - "Put award on hold" (danger, `circle-pause` icon);
  - the close link back to the list (`?status=…`).

  An invalid `scholar` id renders no drawer and no error.
- **Sidebar callout** (`sidebar_callout` block): a yellow-tint box with a clock icon, "Renewals close 15 Nov", "37
  scholars are below the 80% GWA mark this term" and a "Review at-risk scholars" link.
- **Disbursements and apply:** restyle onto the new components (cards, figures box, status text, progress, table
  toolbar). They have no canvas board, so they follow the Scholars page's patterns.

- [ ] **Step 1: Write the failing tests.**
  - **Unit tests:**
    - `test_scholars_mockup_filters_by_status_tab` (`?status=at_risk` lists only At risk rows; the current tab has
      `aria-current`);
    - `test_scholars_drawer_opens_from_the_query`;
    - `test_scholars_bad_scholar_id_has_no_drawer` (`?scholar=abc` and `?scholar=9999` give 200 and no `drawer`);
    - `test_scholars_bad_status_falls_back_to_all`;
    - `test_tier_is_plain_text` (no `status` class inside the tier cell).
  - **e2e tests:**
    - `test_drawer_works_without_javascript` (`java_script_enabled=False`: clicking a name shows the drawer, and its
      close link hides it);
    - `test_drawer_is_full_width_on_a_phone` (375 px: drawer width = viewport width);
    - add `scholars` to the slugs of the existing fit, overflow and money e2e tests.
- [ ] **Step 2: Run them**, expecting FAIL; **implement**; then **compare with the canvas** at 1440 px and 375 px.
- [ ] **Step 3: Run the full gate.**
- [ ] **Step 4: Commit.** `git commit -m "feat: scholars mockup with drawer; restyle disbursements and apply"`

### Task 8: Final verification

- [ ] **Step 1: Run the full gate**, plus `makemigrations --check --dry-run` and
  `manage.py check --deploy --fail-level WARNING` with `DJANGO_DEBUG=false`, `DJANGO_ALLOWED_HOSTS=scholarsync.example`
  and `DJANGO_ENV_FILE=/nonexistent`.
- [ ] **Step 2: Screenshot every mockup and layout demo** at 1440 and 375 into the scratchpad. Check by eye against the
  canvas boards: palette, sidebar, figures box, status text, cards, and no leftover navy or gold.
- [ ] **Step 3: Search for leftovers.** Run `rg -n "navy|#1a3a6b|#f0b323|class=\"tag|appbar|sidenav" frontend templates apps`.
  Expected: no hits, except in tests that assert absence.
- [ ] **Step 4: Update `CLAUDE.md`** only if the file structure changed (for example a new `components.css`), and
  note that M3c is done and the mockup gate awaits Kenneth.
