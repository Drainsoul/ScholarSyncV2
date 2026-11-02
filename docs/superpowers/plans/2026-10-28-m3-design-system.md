# M3 Design System Implementation Plan

**Goal:** Build ScholarSync's design system on `main`:
- tokens, self-hosted fonts and an icon sprite;
- server-rendered components and the five layouts;
- htmx wiring for toasts, dialogs and the bulk bar;
- a dev-only `/_kit/` showing every component in every state;
- five key-screen mockups for Kenneth's approval (the M3 gate).

**Architecture:**
- CSS tokens and component styles live in `frontend/src/styles/` and are bundled by Vite.
- Components are Django templates in `templates/components/` plus a `ui` template-tag library: `icon`, `peso`,
  `field`, `sort_th`, `pagination`.
- Layouts live in `templates/layouts/`, and every page extends one.
- Small strict-TypeScript modules add behaviour on top of server-rendered HTML that already works without JS.
- A new `apps.kit` app (no models) serves the kit and mockups, only when `DJANGO_KIT` is on.
- Playwright tests the browser behaviour under an **enforced** CSP.

**Tech Stack:** existing M2 stack, plus:
- **npm:** `@fontsource/inter` 5.3.0, `@fontsource/poppins` 5.3.0, `lucide-static` 1.63.0 (ISC), `htmx.org` 2.0.11;
- **Python:** `django-htmx` 1.29, `django-template-partials` 25.3; dev: `pytest-playwright` 0.10 (Playwright 1.64,
  Chromium).

**Spec:** `docs/superpowers/specs/2026-10-11-scholarsync-v2-design.md` (rev 2):
- §3 Architecture (`apps/kit`, front-end tree);
- §10 Security (CSP, htmx config);
- §12 Frontend (brand, tokens, components, layouts, icons, design kit, HTMX patterns, TypeScript modules, budget,
  accessibility);
- §13 Testing (e2e from M3); §14 (`DJANGO_KIT`); §15 CI (e2e job); §16 M3.

## Global Constraints
- **Versions:** Python `>=3.13,<3.14`; Django `>=5.2.18,<5.3`; Node `>=22.12`. Pin npm packages exactly
  (`--save-exact`).
- **CSP:** `default-src 'self'`; `script-src 'self'`; `style-src 'self'`; `img-src 'self' data:`; `font-src 'self'`.
  - Templates contain **no inline `<script>`, `<style>`, `style=` or `on*=`**, and no `hx-on`.
  - `apps/core/tests/test_templates.py` already scans for these.
  - Nothing may load from a CDN.
- **htmx config** (exact): `allowEval: false`, `allowScriptTags: false`, `includeIndicatorStyles: false`,
  `selfRequestsOnly: true`, `historyCacheSize: 0`, `refreshOnHistoryMiss: true`.
- **Colour:**
  - `--brand-600 #d10e0f` for red text, buttons and links;
  - `--brand-500 #fd1415`, `--brand-400 #ff4546` and `--accent #ebbf56` are **decorative only** and never `color:`;
  - danger = `--brand-600`, as an **outlined** button;
  - text pairs ≥ 4.5:1; control borders, focus rings and the nav marker ≥ 3:1.
- **Type:** Poppins 600/700 for headings, Inter 400/500/600 for body, Latin subset, self-hosted. Money uses tabular
  figures (`.num`).
- **Money:** `Decimal`, displayed as `₱1,234.50` by the `peso` filter (ROUND_HALF_UP to centavos). `None` displays
  as `—`.
- **Accessibility (WCAG 2.2 AA):**
  - one `h1` per page; a skip link; landmarks; visible focus (3 px `--focus`, gold inside the navy sidebar);
  - 44 px targets (`--control-height: 2.75rem`);
  - every input labelled; help and errors linked with `aria-describedby`; `aria-invalid` on errors;
  - status shown as text plus an icon, never colour alone;
  - `th scope`; `prefers-reduced-motion` respected.
- **No-JS:** every link and form works as plain HTML; JS only enhances.
- **Budget:** JS + CSS ≤ 100 KB gzipped (`npm --prefix frontend run budget`). Fonts are excluded.
- **Kit:**
  - `/_kit/…` answers 404 unless `settings.KIT_ENABLED` (`DJANGO_KIT`, default `DJANGO_DEBUG`);
  - settings refuse to load when `DJANGO_KIT` is true and `VERCEL_ENV=production`;
  - responses carry `X-Robots-Tag: noindex, nofollow`;
  - sample data only: names are Faker `en_PH` output (seed 2026), never real people.
- **Copy:** sentence case; plain verbs; buttons say what happens ("Submit application", not "Submit"). Errors say what
  went wrong and how to fix it, and never apologise. No ALL-CAPS labels, no `→` on buttons.
- **Windows shells:**
  - `python -m uv` (uv isn't on PATH); PowerShell 5.1 has no `&&`;
  - npm installs run **inside** `frontend/` (`Push-Location frontend; npm install …; Pop-Location`);
    `npm --prefix frontend ci|run` work;
  - Python scripts that edit files use `encoding="utf-8"`.
- **Build before pytest:** the `vite_build` fixture reuses an existing `static/dist`. After any front-end change, run
  `npm --prefix frontend run build` before `pytest`.
- **Lockfile:** after each npm install, `frontend/package-lock.json` must still list the Linux native binaries (M2 fix
  `91212ba`). Check that `Select-String -Path frontend/package-lock.json -Pattern 'linux-x64-gnu'` still matches; if
  it doesn't, regenerate the lockfile as in M2.
- **Git:**
  - one commit per task on `main`; Conventional Commits, imperative, subject ≤ 72 characters;
  - stage only the task's files; never push.

## Review Focus
1. **Personal data cached in the browser:** htmx's history cache stores whole-page snapshots in `localStorage`. On a
   shared computer, a student's profile would outlive their session. Expected: after an `hx-push-url` swap,
   `localStorage` is empty.
   - Test: Task 6 `test_htmx_config_is_locked_down` (meta config) and the e2e
     `test_filtering_swaps_only_the_table_and_keeps_history_out_of_storage`.
2. **The kit reachable in production:** a stray `DJANGO_KIT=true` on the production project would expose an
   unauthenticated page tree. Expected: settings refuse to load, naming `DJANGO_KIT`; with the flag unset and
   `DEBUG` off, `/_kit/` is 404.
   - Test: Task 3 `test_kit_refuses_to_load_in_production` and `test_kit_answers_404_when_off`.
3. **User text rendered as HTML:** toast messages from `HX-Trigger`, and form errors that echo submitted values
   (e.g. "Select a valid choice. `<img …>` is not one of…"). Expected: they show as literal text, and no element or
   script is created.
   - Test: Task 4 `test_user_input_in_errors_is_escaped`; Task 6 e2e `test_htmx_toast_shows_text_not_markup`.
4. **Phone width:** most students use phones. Expected: at 375 px no layout or mockup scrolls sideways (wide tables
   scroll inside their own keyboard-focusable region), and the navigation collapses behind a working "Menu" button.
   - Test: Task 8 e2e `test_layout_fits_a_phone_and_nav_toggles`; Task 9 e2e `test_mockup_fits_and_has_no_errors`.
5. **JavaScript off or failed** (old phones, a blocked bundle). Expected:
   - the navigation is visible;
   - dialogs open as full pages;
   - toasts arrive as Django messages;
   - bulk forms still post.
   - Test: Task 6 `test_toast_without_javascript_comes_from_django_messages`; Task 7
     `test_dialog_link_works_without_javascript`; Task 8 `test_nav_is_visible_without_javascript_on_a_phone`.

---

### Task 1: Tokens, fonts, brand marks and base typography

**Files:**
- Modify: `frontend/package.json`, `frontend/package-lock.json` (Fontsource)
- Create: `frontend/src/styles/fonts.css`
- Rewrite: `frontend/src/styles/tokens.css`, `frontend/src/styles/base.css`
- Modify: `frontend/src/main.ts`
- Create: `static/images/favicon.svg`
- Modify: `templates/base.html`, `templates/core/home.html`
- Test: `tests/test_tokens.py`; modify `apps/core/tests/test_home.py`

**Interfaces:**
- Produces:
  - **Palette tokens:** `--brand-700/600/500/400/50`, `--accent`, `--accent-50`, `--navy-800`, `--navy-700`,
    `--navy-muted`, `--info`, `--info-50`, `--success`, `--success-50`, `--warning`, `--warning-50`,
    `--gray-900…50`, `--white`.
  - **Role tokens:** `--text`, `--text-muted`, `--text-inverse`, `--bg`, `--surface`, `--surface-sunken`, `--border`,
    `--border-control`, `--link`, `--link-hover`, `--focus`, `--danger`, `--danger-50`, `--nav-bg`, `--nav-bg-hover`,
    `--nav-text`, `--nav-text-muted`, `--nav-marker`.
  - **Scale tokens:** `--font-heading`, `--font-body`, `--text-sm…4xl`, `--leading-*`, `--measure`, `--space-1…16`,
    `--radius-sm/md/lg/full`, `--shadow-1/2`, `--control-height`, `--sidebar-width`, `--content-max`, `--duration`,
    `--ease`.
  - **Utility classes:** `.container`, `.page`, `.h1`–`.h4`, `.text-muted`, `.text-sm`, `.num`, `.visually-hidden`.
  - **`templates/base.html` blocks:** `title`, `head`, `body` (wraps `<main>`), `content`, `scripts`.

- [ ] **Step 1: Write the failing tests**

`tests/test_tokens.py`:
```python
"""Colour contrast for every token pair the components use (spec §12, WCAG 2.2 AA)."""

import json
import re
from pathlib import Path

import pytest

STYLES = Path(__file__).resolve().parents[1] / "frontend" / "src" / "styles"
DECLARATION = re.compile(r"--([a-z0-9-]+):\s*([^;]+);")
REFERENCE = re.compile(r"^var\(--([a-z0-9-]+)\)$")


def tokens() -> dict[str, str]:
    """Token name -> hex colour, following var(--x) aliases."""
    raw = dict(DECLARATION.findall((STYLES / "tokens.css").read_text(encoding="utf-8")))

    def resolve(name: str) -> str:
        value = raw[name].strip()
        alias = REFERENCE.match(value)
        return resolve(alias.group(1)) if alias else value

    return {name: resolve(name) for name in raw}


def luminance(colour: str) -> float:
    channels = [int(colour[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(a: str, b: str) -> float:
    high, low = sorted((luminance(a), luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


# (foreground, background): text must reach 4.5:1.
TEXT_PAIRS = [
    ("text", "surface"),
    ("text", "bg"),
    ("text-muted", "surface"),
    ("text-muted", "bg"),
    ("text-muted", "surface-sunken"),
    ("link", "surface"),
    ("link", "bg"),
    ("link-hover", "danger-50"),
    ("text-inverse", "brand-600"),
    ("text-inverse", "brand-700"),
    ("danger", "danger-50"),
    ("info", "info-50"),
    ("success", "success-50"),
    ("warning", "warning-50"),
    ("gray-700", "gray-100"),
    ("text", "accent-50"),
    ("nav-text", "nav-bg"),
    ("nav-text-muted", "nav-bg"),
    ("nav-text", "nav-bg-hover"),
]
# Control borders, focus rings and the active-nav marker must reach 3:1 (WCAG 1.4.11).
NON_TEXT_PAIRS = [
    ("border-control", "surface"),
    ("focus", "surface"),
    ("focus", "bg"),
    ("nav-marker", "nav-bg"),
    ("nav-marker", "nav-bg-hover"),
]
DECORATIVE_AS_TEXT = re.compile(r"(?<![-\w])color:\s*var\(--(brand-500|brand-400|accent|nav-marker)\)")


@pytest.mark.parametrize(("foreground", "background"), TEXT_PAIRS)
def test_text_pairs_reach_aa(foreground, background):
    colours = tokens()
    ratio = contrast(colours[foreground], colours[background])
    assert ratio >= 4.5, f"--{foreground} on --{background} is {ratio:.2f}:1"


@pytest.mark.parametrize(("foreground", "background"), NON_TEXT_PAIRS)
def test_non_text_pairs_reach_3_to_1(foreground, background):
    colours = tokens()
    ratio = contrast(colours[foreground], colours[background])
    assert ratio >= 3.0, f"--{foreground} on --{background} is {ratio:.2f}:1"


def test_decorative_colours_are_never_text():
    offenders = [
        f"{path.name}: {match.group(0)}"
        for path in STYLES.rglob("*.css")
        for match in DECORATIVE_AS_TEXT.finditer(path.read_text(encoding="utf-8"))
    ]
    assert offenders == []


def test_fonts_are_self_hosted(vite_build):
    manifest = json.loads(vite_build.read_text(encoding="utf-8"))
    dist = vite_build.parents[1]
    css = "".join(
        (dist / name).read_text(encoding="utf-8") for name in manifest["src/main.ts"]["css"]
    )
    assert "@font-face" in css
    assert "Inter" in css
    assert "Poppins" in css
    assert ".woff2" in css
    assert "//fonts." not in css
```

Append to `apps/core/tests/test_home.py`:
```python
def test_home_links_the_favicon(client, vite_build):
    body = client.get("/").content.decode()
    assert '<link rel="icon" href="/static/images/favicon.svg" type="image/svg+xml">' in body
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m uv run pytest tests/test_tokens.py apps/core/tests/test_home.py -q`
Expected: FAIL. `KeyError: 'text'` (the role tokens don't exist yet), the font assertions fail, and so does the
favicon test.

- [ ] **Step 3: Install the fonts**

```powershell
Push-Location frontend; npm install --save-dev --save-exact @fontsource/inter@5.3.0 @fontsource/poppins@5.3.0; Pop-Location
Select-String -Path frontend/package-lock.json -Pattern 'linux-x64-gnu' | Select-Object -First 1
```
Expected: the install succeeds, and `Select-String` prints a match.

- [ ] **Step 4: Write the fonts, tokens and base styles**

`frontend/src/styles/fonts.css`:
```css
/* Self-hosted Latin subsets (spec §12): no runtime CDN. Latin covers Filipino's ñ. */
@import "@fontsource/inter/latin-400.css";
@import "@fontsource/inter/latin-500.css";
@import "@fontsource/inter/latin-600.css";
@import "@fontsource/poppins/latin-600.css";
@import "@fontsource/poppins/latin-700.css";
```

`frontend/src/styles/tokens.css`:
```css
/* Design tokens (spec §12). tests/test_tokens.py checks every pair the components use for WCAG AA. */
:root {
  /* Palette */
  --brand-700: #a70b0c;
  --brand-600: #d10e0f; /* red text, buttons and links: 5.6:1 on white */
  --brand-500: #fd1415; /* decorative only */
  --brand-400: #ff4546; /* decorative only */
  --brand-50: #fef2f2;
  --accent: #ebbf56; /* gold, decorative only: 1.7:1 on white, 7:1 on navy */
  --accent-50: #fdf6e3;
  --navy-800: #1b3366;
  --navy-700: #24407a;
  --navy-muted: #c7d2e8;
  --info: #27488b;
  --info-50: #eef2fa;
  --success: #047857;
  --success-50: #ecfdf5;
  --warning: #b45309;
  --warning-50: #fffbeb;
  --gray-900: #111827;
  --gray-800: #1f2937;
  --gray-700: #374151;
  --gray-600: #4b5563;
  --gray-500: #6b7280;
  --gray-400: #9ca3af;
  --gray-300: #d1d5db;
  --gray-200: #e5e7eb;
  --gray-100: #f3f4f6;
  --gray-50: #f9fafb;
  --white: #ffffff;

  /* Roles: components use these, so a dark theme can remap them later */
  --text: var(--gray-900);
  --text-muted: var(--gray-600);
  --text-inverse: var(--white);
  --bg: var(--gray-50);
  --surface: var(--white);
  --surface-sunken: var(--gray-100);
  --border: var(--gray-200);
  --border-control: var(--gray-500);
  --link: var(--brand-600);
  --link-hover: var(--brand-700);
  --focus: var(--info);
  --danger: var(--brand-600);
  --danger-50: var(--brand-50);
  --nav-bg: var(--navy-800);
  --nav-bg-hover: var(--navy-700);
  --nav-text: var(--white);
  --nav-text-muted: var(--navy-muted);
  --nav-marker: var(--accent);

  /* Type: a 1.25 (major third) scale */
  --font-heading: "Poppins", system-ui, sans-serif;
  --font-body: "Inter", system-ui, -apple-system, "Segoe UI", sans-serif;
  --text-sm: 0.875rem;
  --text-base: 1rem;
  --text-lg: 1.125rem;
  --text-xl: 1.25rem;
  --text-2xl: 1.5625rem;
  --text-3xl: 1.9531rem;
  --text-4xl: 2.4414rem;
  --leading-tight: 1.25;
  --leading-body: 1.5;
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

  /* Shape: radius grows with the size of the thing; shadows only on things that float */
  --radius-sm: 4px;
  --radius-md: 8px;
  --radius-lg: 12px;
  --radius-full: 999px;
  --shadow-1: 0 1px 2px rgb(17 24 39 / 0.06), 0 1px 3px rgb(17 24 39 / 0.08);
  --shadow-2: 0 16px 40px -12px rgb(17 24 39 / 0.28);

  /* Sizes and motion */
  --control-height: 2.75rem; /* 44 px touch target */
  --sidebar-width: 16rem;
  --content-max: 76rem;
  --duration: 150ms;
  --ease: cubic-bezier(0.2, 0, 0, 1);
}
```

`frontend/src/styles/base.css`:
```css
*,
*::before,
*::after {
  box-sizing: border-box;
}

/* Author display rules (e.g. .icon-btn { display: grid }) must not un-hide [hidden] elements. */
[hidden] {
  /* biome-ignore lint/complexity/noImportantStyles: the hidden attribute must always win */
  display: none !important;
}

html {
  -webkit-text-size-adjust: 100%;
  text-size-adjust: 100%;
}

body {
  margin: 0;
  font-family: var(--font-body);
  font-size: var(--text-base);
  line-height: var(--leading-body);
  color: var(--text);
  background: var(--bg);
}

h1,
h2,
h3,
h4,
.h1,
.h2,
.h3,
.h4 {
  margin: 0 0 var(--space-4);
  font-family: var(--font-heading);
  font-weight: 600;
  line-height: var(--leading-tight);
  color: var(--text);
  text-wrap: balance;
}

h1,
.h1 {
  font-size: var(--text-3xl);
  font-weight: 700;
}

h2,
.h2 {
  font-size: var(--text-2xl);
}

h3,
.h3 {
  font-size: var(--text-xl);
}

h4,
.h4 {
  font-size: var(--text-lg);
}

p {
  margin: 0 0 var(--space-4);
  max-width: var(--measure);
}

a {
  color: var(--link);
  text-underline-offset: 0.15em;
}

a:hover {
  color: var(--link-hover);
}

code {
  font-size: 0.9em;
}

.container {
  width: 100%;
  max-width: var(--content-max);
  margin-inline: auto;
  padding-inline: var(--space-4);
}

@media (min-width: 40rem) {
  .container {
    padding-inline: var(--space-6);
  }
}

.page {
  padding-block: var(--space-8) var(--space-16);
}

.text-muted {
  color: var(--text-muted);
}

.text-sm {
  font-size: var(--text-sm);
}

.num {
  font-variant-numeric: tabular-nums;
}

.visually-hidden {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
  border: 0;
}

.skip-link {
  position: absolute;
  z-index: 100;
  left: var(--space-2);
  top: -3rem;
  padding: var(--space-2) var(--space-4);
  background: var(--surface);
  color: var(--link);
  border-radius: var(--radius-md);
}

.skip-link:focus {
  top: var(--space-2);
}

:focus-visible {
  outline: 3px solid var(--focus);
  outline-offset: 2px;
}

main:focus {
  outline: none;
}

.icon {
  width: 1.25em;
  height: 1.25em;
  flex: none;
  vertical-align: -0.25em;
}

@media (prefers-reduced-motion: reduce) {
  * {
    /* biome-ignore lint/complexity/noImportantStyles: reduced motion must override every component rule */
    animation: none !important;
    /* biome-ignore lint/complexity/noImportantStyles: reduced motion must override every component rule */
    transition: none !important;
  }
}
```

`frontend/src/main.ts`:
```ts
import "./styles/fonts.css";
import "./styles/tokens.css";
import "./styles/base.css";

document.documentElement.classList.add("js");
```

- [ ] **Step 5: Add the favicon and update the base template**

`static/images/favicon.svg`:
```svg
<!-- Academic cap: Heroicons v1 (MIT, Refactoring UI Inc.), the ScholarSync v1 mark -->
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#d10e0f" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 14l9-5-9-5-9 5 9 5z"/><path d="M12 14l6.16-3.422a12.083 12.083 0 01.665 6.479A11.952 11.952 0 0012 20.055a11.952 11.952 0 00-6.824-2.998 12.083 12.083 0 01.665-6.479L12 14z"/></svg>
```

`templates/base.html`:
```django
{% load static django_vite %}<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block title %}ScholarSync{% endblock %} · City of Taguig</title>
  <link rel="icon" href="{% static 'images/favicon.svg' %}" type="image/svg+xml">
  <meta name="theme-color" content="#1b3366">
  {% vite_hmr_client %}
  {% vite_asset 'src/main.ts' %}
  {% block head %}{% endblock %}
</head>
<body>
  <a class="skip-link" href="#main">Skip to content</a>
  {% block body %}
  <main id="main" tabindex="-1">
    {% block content %}{% endblock %}
  </main>
  {% endblock %}
  {% block scripts %}{% endblock %}
</body>
</html>
```

`templates/core/home.html`:
```django
{% extends "base.html" %}
{% block title %}Scholarships{% endblock %}
{% block content %}
  <div class="container page">
    <h1>ScholarSync</h1>
    <p>The City of Taguig scholarship platform is being rebuilt. Programs and applications open here soon.</p>
  </div>
{% endblock %}
```

- [ ] **Step 6: Build and run the tests to verify they pass**

```powershell
npm --prefix frontend run build
python -m uv run pytest tests/test_tokens.py apps/core/tests -q
npm --prefix frontend run typecheck; npm --prefix frontend run check; npm --prefix frontend run budget
```
Expected: all PASS. Biome is clean; if it reports formatting, run `Push-Location frontend; npx biome check --write .;
Pop-Location`. Budget stays well under 100 KB.

- [ ] **Step 7: Commit**

```powershell
git add frontend/package.json frontend/package-lock.json frontend/src/main.ts frontend/src/styles/fonts.css frontend/src/styles/tokens.css frontend/src/styles/base.css static/images/favicon.svg templates/base.html templates/core/home.html tests/test_tokens.py apps/core/tests/test_home.py
git commit -m "feat: add design tokens, self-hosted fonts and base typography"
```

---

### Task 2: Icon sprite and the `ui` tag library (`icon`, `peso`)

**Files:**
- Modify: `frontend/package.json` (lucide-static 1.63.0; build runs the sprite script), `frontend/package-lock.json`
- Create: `frontend/src/icons/icons.json`, `frontend/src/icons/logo.svg`, `frontend/scripts/sprite.mjs`
- Create: `apps/core/templatetags/__init__.py`, `apps/core/templatetags/ui.py`
- Modify: `conftest.py` (rebuild when the sprite is missing)
- Test: `apps/core/tests/test_ui_tags.py`, `tests/test_icons.py`

**Interfaces:**
- Consumes: `.icon` class (Task 1).
- Produces:
  - `static/dist/icons.svg`, with one `<symbol id="<name>">` per name in `icons.json`, plus `logo`;
  - `{% load ui %}`;
  - `{% icon "name" %}`, which renders `<svg class="icon" aria-hidden="true" focusable="false"><use
    href="/static/dist/icons.svg#name"></use></svg>`;
  - `{% icon "name" "Label" %}`, which renders `role="img" aria-label="Label"`;
  - the `{{ value|peso }}` filter;
  - Python: `apps.core.templatetags.ui.icon(name: str, label: str = "") -> SafeString`,
    `peso(value: Decimal | int | None) -> str`.

- [ ] **Step 1: Write the failing tests**

`apps/core/tests/test_ui_tags.py`:
```python
from decimal import Decimal

import pytest
from django.template import Context, Template

from apps.core.templatetags.ui import peso


def render(source: str, **context) -> str:
    return Template("{% load ui %}" + source).render(Context(context))


def test_icon_is_decorative_by_default():
    assert render('{% icon "check" %}') == (
        '<svg class="icon" aria-hidden="true" focusable="false">'
        '<use href="/static/dist/icons.svg#check"></use></svg>'
    )


def test_icon_with_a_label_is_announced():
    html = render('{% icon "check" "Approved" %}')
    assert 'role="img" aria-label="Approved"' in html
    assert "aria-hidden" not in html


def test_icon_label_is_escaped():
    assert "&lt;b&gt;" in render('{% icon "check" label %}', label="<b>")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (Decimal("1234.5"), "₱1,234.50"),
        (0, "₱0.00"),
        (Decimal("-50"), "-₱50.00"),
        (Decimal("0.005"), "₱0.01"),
        (Decimal("-0.001"), "₱0.00"),
        (Decimal("1000000"), "₱1,000,000.00"),
        (None, "—"),
    ],
)
def test_peso(value, expected):
    assert render("{{ value|peso }}", value=value) == expected


def test_peso_rejects_floats():
    with pytest.raises(TypeError, match="Decimal"):
        peso(0.1)  # type: ignore[arg-type]
```

`tests/test_icons.py`:
```python
"""Every icon a template names exists in the sprite (spec §12)."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ICONS = ROOT / "frontend" / "src" / "icons"
SPRITE = ROOT / "static" / "dist" / "icons.svg"
USES = [
    re.compile(r"""\{%\s*icon\s+["']([a-z0-9-]+)["']"""),  # {% icon "name" %}
    re.compile(r"""\bicon=["']([a-z0-9-]+)["']"""),  # {% include … with icon="name" %}
]


def known_icons() -> set[str]:
    names = set(json.loads((ICONS / "icons.json").read_text(encoding="utf-8")))
    return names | {path.stem for path in ICONS.glob("*.svg")}


def test_every_icon_named_in_templates_is_in_the_sprite_list():
    templates = [*ROOT.glob("templates/**/*.html"), *ROOT.glob("apps/**/templates/**/*.html")]
    used = {
        name: str(path.relative_to(ROOT))
        for path in templates
        for pattern in USES
        for name in pattern.findall(path.read_text(encoding="utf-8"))
    }
    assert {name: where for name, where in used.items() if name not in known_icons()} == {}


def test_sprite_has_one_symbol_per_icon(vite_build):
    ids = re.findall(r'<symbol id="([a-z0-9-]+)"', SPRITE.read_text(encoding="utf-8"))
    assert sorted(ids) == sorted(known_icons())
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m uv run pytest apps/core/tests/test_ui_tags.py tests/test_icons.py -q`
Expected: FAIL. `'ui' is not a registered tag library` and `ModuleNotFoundError: apps.core.templatetags`;
`FileNotFoundError` for `icons.json`.

- [ ] **Step 3: Install Lucide and write the sprite builder**

```powershell
Push-Location frontend; npm install --save-dev --save-exact lucide-static@1.63.0; Pop-Location
Select-String -Path frontend/package-lock.json -Pattern 'linux-x64-gnu' | Select-Object -First 1
```

In `frontend/package.json`, change `scripts.build` and add `scripts.sprite`:
```json
    "build": "vite build && node scripts/sprite.mjs",
    "sprite": "node scripts/sprite.mjs",
```

`frontend/src/icons/icons.json` (every name exists in lucide-static 1.63.0; checked 2026-10-28):
```json
[
  "arrow-down",
  "arrow-up",
  "banknote",
  "bell",
  "building-2",
  "calendar",
  "chart-column",
  "check",
  "chevron-down",
  "chevron-left",
  "chevron-right",
  "chevrons-up-down",
  "circle-alert",
  "circle-check",
  "clipboard-check",
  "download",
  "eye",
  "file-check",
  "file-text",
  "file-x",
  "filter",
  "hand-coins",
  "inbox",
  "info",
  "layout-dashboard",
  "list-checks",
  "log-out",
  "menu",
  "pencil",
  "plus",
  "school",
  "search",
  "settings",
  "shield-check",
  "trash-2",
  "triangle-alert",
  "upload",
  "user",
  "users",
  "wallet",
  "x"
]
```

`frontend/src/icons/logo.svg`:
```svg
<!-- Academic cap: Heroicons v1 (MIT, Refactoring UI Inc.), the ScholarSync v1 mark -->
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M12 14l9-5-9-5-9 5 9 5z"/><path d="M12 14l6.16-3.422a12.083 12.083 0 01.665 6.479A11.952 11.952 0 0012 20.055a11.952 11.952 0 00-6.824-2.998 12.083 12.083 0 01.665-6.479L12 14z"/></svg>
```

`frontend/scripts/sprite.mjs`:
```js
// Builds static/dist/icons.svg (spec §12): one <symbol> per Lucide icon named in src/icons/icons.json,
// plus our own icons in src/icons/*.svg. Runs after `vite build`, which empties static/dist.
// A misspelt name fails the build (readFileSync throws ENOENT).
import { readdirSync, readFileSync, writeFileSync } from "node:fs";
import { basename, dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const iconsDir = resolve(here, "../src/icons");
const lucideDir = resolve(here, "../node_modules/lucide-static/icons");
const out = resolve(here, "../../static/dist/icons.svg");
const ATTRS =
  'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" ' +
  'stroke-linecap="round" stroke-linejoin="round"';

function inner(file) {
  const match = readFileSync(file, "utf8").match(/<svg[^>]*>([\s\S]*?)<\/svg>/);
  if (!match) throw new Error(`sprite: no <svg> element in ${file}`);
  return match[1].replace(/\s+/g, " ").trim();
}

const symbols = new Map();
for (const name of JSON.parse(readFileSync(resolve(iconsDir, "icons.json"), "utf8"))) {
  symbols.set(name, inner(resolve(lucideDir, `${name}.svg`)));
}
for (const file of readdirSync(iconsDir).filter((f) => f.endsWith(".svg"))) {
  const name = basename(file, ".svg");
  if (symbols.has(name)) throw new Error(`sprite: ${name}.svg clashes with a Lucide icon`);
  symbols.set(name, inner(resolve(iconsDir, file)));
}

const body = [...symbols].map(([id, svg]) => `<symbol id="${id}" ${ATTRS}>${svg}</symbol>`);
writeFileSync(out, `<svg xmlns="http://www.w3.org/2000/svg">${body.join("")}</svg>\n`);
console.log(`sprite: ${symbols.size} icons`);
```

- [ ] **Step 4: Write the tag library**

`apps/core/templatetags/__init__.py`: empty.

`apps/core/templatetags/ui.py`:
```python
"""Design-system template tags (spec §12). Load with {% load ui %}."""

from decimal import ROUND_HALF_UP, Decimal

from django import template
from django.templatetags.static import static
from django.utils.html import format_html
from django.utils.safestring import SafeString

register = template.Library()

CENTAVO = Decimal("0.01")


@register.simple_tag
def icon(name: str, label: str = "") -> SafeString:
    """An icon from the sprite. Decorative unless it has a label (then it is the only content)."""
    href = f"{static('dist/icons.svg')}#{name}"
    if label:
        return format_html(
            '<svg class="icon" role="img" aria-label="{}" focusable="false"><use href="{}"></use></svg>',
            label,
            href,
        )
    return format_html(
        '<svg class="icon" aria-hidden="true" focusable="false"><use href="{}"></use></svg>', href
    )


@register.filter
def peso(value: Decimal | int | None) -> str:
    """₱1,234.50. Money is Decimal (CLAUDE.md); a float here is a bug, so it raises."""
    if value is None:
        return "—"
    if isinstance(value, float):
        raise TypeError("peso() takes Decimal or int, not float")
    amount = Decimal(value).quantize(CENTAVO, rounding=ROUND_HALF_UP)
    sign = "-" if amount < 0 else ""
    return f"{sign}₱{abs(amount):,.2f}"
```

In `conftest.py`, make `vite_build` rebuild when the sprite is missing as well as the manifest:
```python
SPRITE = ROOT / "static" / "dist" / "icons.svg"
```
and change `if not MANIFEST.exists():` to `if not (MANIFEST.exists() and SPRITE.exists()):`.

- [ ] **Step 5: Build and run the tests to verify they pass**

```powershell
npm --prefix frontend run build
python -m uv run pytest apps/core/tests/test_ui_tags.py tests/test_icons.py -q
python -m uv run mypy .
npm --prefix frontend run check
```
Expected: the build prints `sprite: 42 icons`; the tests PASS; mypy and Biome are clean.

- [ ] **Step 6: Commit**

```powershell
git add frontend/package.json frontend/package-lock.json frontend/src/icons frontend/scripts/sprite.mjs apps/core/templatetags conftest.py apps/core/tests/test_ui_tags.py tests/test_icons.py
git commit -m "feat: add Lucide icon sprite and icon/peso template tags"
```

---

### Task 3: Design-kit app, its production guard and the Playwright harness

**Files:**
- Modify: `pyproject.toml` (+`pytest-playwright`, `e2e` marker), `uv.lock`
- Modify: `config/settings.py` (`apps.kit`, `KIT_ENABLED` + guard), `config/urls.py`, `.env.example`
- Create: `config/e2e_settings.py`
- Create: `apps/kit/__init__.py`, `apps/kit/apps.py`, `apps/kit/urls.py`, `apps/kit/views.py`
- Create: `apps/kit/templates/kit/base.html`, `kit/index.html`, `kit/sections/{colour,type,icons}.html`
- Create: `frontend/src/kit.ts`, `frontend/src/styles/kit.css`; modify `frontend/vite.config.ts` (second entry)
- Create: `tests/e2e/__init__.py`, `tests/e2e/conftest.py`, `tests/e2e/test_kit.py`
- Modify: `.github/workflows/ci.yml` (e2e job), `CLAUDE.md`, `README.md`
- Test: `apps/kit/tests/__init__.py`, `apps/kit/tests/test_kit.py`; modify `config/tests/test_settings.py`

**Interfaces:**
- Consumes: `{% icon %}` (Task 2), tokens and utilities (Task 1).
- Produces:
  - `settings.KIT_ENABLED: bool`;
  - `apps.kit.views.kit_only(view) -> view` (404 when off; adds `X-Robots-Tag`);
  - `apps.kit.views.SECTIONS: list[tuple[str, str]]` (`id`, `title`). The index renders
    `kit/sections/<id>.html` for each entry, so later tasks append to it;
  - `apps.kit.views.index_context(request) -> dict[str, object]` (later tasks extend it);
  - `apps.kit.views.icon_names() -> list[str]`;
  - URL names `kit:index` (`/_kit/`);
  - e2e fixture `console_errors: list[str]`;
  - every e2e module sets `pytestmark = pytest.mark.e2e`.

- [ ] **Step 1: Write the failing tests**

`apps/kit/tests/__init__.py`: empty.

`apps/kit/tests/test_kit.py`:
```python
import re
from pathlib import Path

import pytest

from apps.kit.views import SWATCHES, icon_names

STYLES = Path(__file__).resolve().parents[3] / "frontend" / "src" / "styles"


@pytest.fixture
def kit_on(settings):
    settings.KIT_ENABLED = True


def test_kit_answers_404_when_off(client, settings):
    settings.KIT_ENABLED = False
    assert client.get("/_kit/").status_code == 404


def test_kit_index_renders_the_foundations(client, kit_on, vite_build):
    response = client.get("/_kit/")
    body = response.content.decode()
    assert response.status_code == 200
    assert response["X-Robots-Tag"] == "noindex, nofollow"
    assert body.count("<h1") == 1
    for section in ("colour", "type", "icons"):
        assert f'<section class="kit-section" id="{section}"' in body
    assert "/static/dist/assets/kit-" in body


def test_kit_shows_every_icon(client, kit_on, vite_build):
    body = client.get("/_kit/").content.decode()
    for name in icon_names():
        assert f"icons.svg#{name}" in body


def test_every_swatch_is_a_token_with_a_kit_style():
    tokens = (STYLES / "tokens.css").read_text(encoding="utf-8")
    kit = (STYLES / "kit.css").read_text(encoding="utf-8")
    for name in SWATCHES:
        assert re.search(rf"--{name}:", tokens), name
        assert re.search(rf"\.kit-swatch--{name}\s*\{{\s*background:\s*var\(--{name}\);", kit), name
```

Append to `config/tests/test_settings.py`:
```python
def _kit_env(tmp_path, **extra):
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in {"DJANGO_DEBUG", "DJANGO_KIT", "VERCEL_ENV"}
    }
    env.update(
        {
            "DJANGO_SECRET_KEY": "x" * 50,
            "DATABASE_URL": "postgres://u:p@localhost:5433/db",
            "DJANGO_ENV_FILE": str(tmp_path / "absent.env"),
            **extra,
        }
    )
    return env


def _kit_enabled(env):
    return subprocess.run(  # noqa: S603
        [sys.executable, "-c", "import config.settings as s; print(s.KIT_ENABLED)"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_kit_refuses_to_load_in_production(tmp_path):
    result = _kit_enabled(_kit_env(tmp_path, DJANGO_KIT="true", VERCEL_ENV="production"))
    assert result.returncode != 0
    assert "DJANGO_KIT" in result.stderr


def test_kit_is_off_by_default_and_allowed_on_previews(tmp_path):
    assert _kit_enabled(_kit_env(tmp_path)).stdout.strip() == "False"
    preview = _kit_enabled(_kit_env(tmp_path, DJANGO_KIT="true", VERCEL_ENV="preview"))
    assert preview.stdout.strip() == "True"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m uv run pytest apps/kit config/tests/test_settings.py -q`
Expected: FAIL. `ModuleNotFoundError: No module named 'apps.kit'`; the settings tests fail on `KIT_ENABLED`.

- [ ] **Step 3: Add pytest-playwright and the marker**

```powershell
python -m uv add --dev "pytest-playwright>=0.10"
python -m uv run playwright install chromium
```
In `pyproject.toml` `[tool.pytest.ini_options]`, set:
```toml
addopts = "-q -m 'not e2e'"
markers = ["e2e: Playwright browser tests; run with -m e2e --ds=config.e2e_settings --browser chromium"]
```

- [ ] **Step 4: Settings, the guard and the e2e settings**

In `config/settings.py`:
- add `from django.core.exceptions import ImproperlyConfigured` to the imports;
- add `"apps.kit"` after `"apps.core"` in `INSTALLED_APPS`;
- add after the `# Core` block's `CSRF_TRUSTED_ORIGINS` line:
```python
# Design kit (spec §12): /_kit/ answers 404 unless enabled, and is never allowed in production.
KIT_ENABLED = env.bool("DJANGO_KIT", DEBUG)
if KIT_ENABLED and os.environ.get("VERCEL_ENV") == "production":
    raise ImproperlyConfigured("DJANGO_KIT must be off in production (VERCEL_ENV=production).")
```

`config/e2e_settings.py`:
```python
"""Settings for the Playwright suite: pytest -m e2e --ds=config.e2e_settings --browser chromium.

Production security, except what an HTTP live server can't do: no HTTPS redirect, no Secure cookies.
The CSP is enforced (not report-only), so an inline script or style fails a test. The design kit is on.
"""

import os

os.environ["DJANGO_DEBUG"] = "false"
os.environ["DJANGO_SECURE_SSL_REDIRECT"] = "false"
os.environ["CSP_REPORT_ONLY"] = "false"
os.environ["DJANGO_KIT"] = "true"
# Playwright's sync API runs an event loop in the test thread; Django's ORM refuses to run there without this.
os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"

from config.settings import *  # noqa: E402, F403

ALLOWED_HOSTS = ["localhost", "127.0.0.1"]
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
STORAGES = {
    **STORAGES,  # noqa: F405
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
```

`.env.example`, after `CSP_REPORT_ONLY=true`:
```
# Design kit at /_kit/ (defaults to DJANGO_DEBUG; refused when VERCEL_ENV=production)
DJANGO_KIT=true
```

`config/urls.py`:
```python
from django.urls import include, path

urlpatterns = [
    path("", include("apps.core.urls")),
    path("_kit/", include("apps.kit.urls")),
]
```

- [ ] **Step 5: The kit app**

`apps/kit/__init__.py`: empty.

`apps/kit/apps.py`:
```python
from django.apps import AppConfig


class KitConfig(AppConfig):
    name = "apps.kit"
    label = "kit"
```

`apps/kit/urls.py`:
```python
from django.urls import path

from apps.kit import views

app_name = "kit"

urlpatterns = [
    path("", views.index, name="index"),
]
```

`apps/kit/views.py`:
```python
"""Design kit (spec §12): every component in every state, and the key-screen mockups.

Development only: every view answers 404 unless settings.KIT_ENABLED, and pages are never indexed.
"""

import json
from collections.abc import Callable
from functools import wraps

from django.conf import settings
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_safe

View = Callable[..., HttpResponse]

ICONS_DIR = settings.BASE_DIR / "frontend" / "src" / "icons"

# (section id, title); the index includes kit/sections/<id>.html for each, in order.
SECTIONS: list[tuple[str, str]] = [
    ("colour", "Colour"),
    ("type", "Type"),
    ("icons", "Icons"),
]

SWATCHES = [
    "brand-700", "brand-600", "brand-500", "brand-400", "brand-50", "accent", "accent-50",
    "navy-800", "navy-700", "navy-muted", "info", "info-50", "success", "success-50",
    "warning", "warning-50", "gray-900", "gray-800", "gray-700", "gray-600", "gray-500",
    "gray-400", "gray-300", "gray-200", "gray-100", "gray-50", "white",
]  # fmt: skip


def kit_only(view: View) -> View:
    @wraps(view)
    def wrapper(request: HttpRequest, *args: object, **kwargs: object) -> HttpResponse:
        if not settings.KIT_ENABLED:
            raise Http404
        response = view(request, *args, **kwargs)
        response["X-Robots-Tag"] = "noindex, nofollow"
        return response

    return wrapper


def icon_names() -> list[str]:
    names: list[str] = json.loads((ICONS_DIR / "icons.json").read_text(encoding="utf-8"))
    return names + sorted(path.stem for path in ICONS_DIR.glob("*.svg"))


def index_context(request: HttpRequest) -> dict[str, object]:
    return {
        "sections": [
            {"id": key, "title": title, "template": f"kit/sections/{key}.html"}
            for key, title in SECTIONS
        ],
        "swatches": SWATCHES,
        "icons": icon_names(),
    }


@kit_only
@require_safe
def index(request: HttpRequest) -> HttpResponse:
    return render(request, "kit/index.html", index_context(request))
```

`apps/kit/templates/kit/base.html`:
```django
{% extends "base.html" %}{% load django_vite %}
{% block title %}Design kit{% endblock %}
{% block head %}{% vite_asset 'src/kit.ts' %}{% endblock %}
{% block body %}
<header class="kit-header">
  <div class="container"><a class="kit-header__home" href="{% url 'kit:index' %}">ScholarSync design kit</a></div>
</header>
<main id="main" tabindex="-1" class="container page">
  {% block content %}{% endblock %}
</main>
{% endblock %}
```

`apps/kit/templates/kit/index.html`:
```django
{% extends "kit/base.html" %}
{% block content %}
<h1>Design kit</h1>
<p>Every component in every state, built from <code>frontend/src/styles</code> and <code>templates/components</code> (spec §12). Sample data only.</p>
<nav class="kit-toc" aria-label="Sections">
  <ul>{% for section in sections %}<li><a href="#{{ section.id }}">{{ section.title }}</a></li>{% endfor %}</ul>
</nav>
{% for section in sections %}{% include section.template %}{% endfor %}
{% endblock %}
```

`apps/kit/templates/kit/sections/colour.html`:
```django
<section class="kit-section" id="colour" aria-labelledby="colour-title">
  <h2 id="colour-title">Colour</h2>
  <p>Brand red is for actions and links. Gold and the lighter reds are decorative only; tests/test_tokens.py checks every text pair for AA contrast.</p>
  <ul class="kit-swatches">
    {% for name in swatches %}<li><span class="kit-swatch kit-swatch--{{ name }}"></span><code>--{{ name }}</code></li>{% endfor %}
  </ul>
</section>
```

`apps/kit/templates/kit/sections/type.html`:
```django
<section class="kit-section" id="type" aria-labelledby="type-title">
  <h2 id="type-title">Type</h2>
  <p class="h1">Heading 1, Poppins 700</p>
  <p class="h2">Heading 2, Poppins 600</p>
  <p class="h3">Heading 3, Poppins 600</p>
  <p class="h4">Heading 4, Poppins 600</p>
  <p>Body text is Inter 400 at 1 rem with a 1.5 line height. Paragraphs stop at about 68 characters so long explanations stay easy to read on a laptop.</p>
  <p class="text-muted">Muted text is for hints and metadata.</p>
  <p class="text-sm">Small text, 0.875 rem, is for tables and captions.</p>
  <p class="num">Tabular figures keep money aligned: ₱1,234,567.00 and ₱98,000.50</p>
  <p><a href="#type">A text link</a></p>
</section>
```

`apps/kit/templates/kit/sections/icons.html`:
```django
{% load ui %}
<section class="kit-section" id="icons" aria-labelledby="icons-title">
  <h2 id="icons-title">Icons</h2>
  <p>Lucide icons from one sprite. Icons are decorative by default; give one a label when it is the only content of a control.</p>
  <ul class="kit-icons">
    {% for name in icons %}<li>{% icon name %}<code>{{ name }}</code></li>{% endfor %}
  </ul>
</section>
```

`frontend/src/kit.ts`:
```ts
import "./styles/kit.css";
```

`frontend/src/styles/kit.css`:
```css
/* Design-kit pages only (apps/kit); not part of the app bundle. */
.kit-header {
  background: var(--nav-bg);
}

.kit-header__home {
  display: inline-flex;
  align-items: center;
  min-height: 3.5rem;
  color: var(--nav-text);
  font-family: var(--font-heading);
  font-weight: 600;
  text-decoration: none;
}

.kit-header__home:hover {
  color: var(--nav-text);
  text-decoration: underline;
}

.kit-header :focus-visible {
  outline-color: var(--nav-marker);
}

.kit-toc ul {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2) var(--space-4);
  margin: 0 0 var(--space-8);
  padding: 0;
  list-style: none;
}

.kit-section {
  padding-block: var(--space-8);
  border-top: 1px solid var(--border);
}

.kit-state {
  margin-bottom: var(--space-8);
}

.kit-state > h3 {
  font-size: var(--text-base);
  color: var(--text-muted);
}

.kit-swatches,
.kit-icons {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(10rem, 1fr));
  gap: var(--space-3);
  margin: 0;
  padding: 0;
  list-style: none;
}

.kit-swatches li,
.kit-icons li {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  font-size: var(--text-sm);
}

.kit-swatch {
  width: 2.5rem;
  height: 2.5rem;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
}

.kit-swatch--brand-700 {
  background: var(--brand-700);
}

.kit-swatch--brand-600 {
  background: var(--brand-600);
}

.kit-swatch--brand-500 {
  background: var(--brand-500);
}

.kit-swatch--brand-400 {
  background: var(--brand-400);
}

.kit-swatch--brand-50 {
  background: var(--brand-50);
}

.kit-swatch--accent {
  background: var(--accent);
}

.kit-swatch--accent-50 {
  background: var(--accent-50);
}

.kit-swatch--navy-800 {
  background: var(--navy-800);
}

.kit-swatch--navy-700 {
  background: var(--navy-700);
}

.kit-swatch--navy-muted {
  background: var(--navy-muted);
}

.kit-swatch--info {
  background: var(--info);
}

.kit-swatch--info-50 {
  background: var(--info-50);
}

.kit-swatch--success {
  background: var(--success);
}

.kit-swatch--success-50 {
  background: var(--success-50);
}

.kit-swatch--warning {
  background: var(--warning);
}

.kit-swatch--warning-50 {
  background: var(--warning-50);
}

.kit-swatch--gray-900 {
  background: var(--gray-900);
}

.kit-swatch--gray-800 {
  background: var(--gray-800);
}

.kit-swatch--gray-700 {
  background: var(--gray-700);
}

.kit-swatch--gray-600 {
  background: var(--gray-600);
}

.kit-swatch--gray-500 {
  background: var(--gray-500);
}

.kit-swatch--gray-400 {
  background: var(--gray-400);
}

.kit-swatch--gray-300 {
  background: var(--gray-300);
}

.kit-swatch--gray-200 {
  background: var(--gray-200);
}

.kit-swatch--gray-100 {
  background: var(--gray-100);
}

.kit-swatch--gray-50 {
  background: var(--gray-50);
}

.kit-swatch--white {
  background: var(--white);
}
```

In `frontend/vite.config.ts`, add the second entry:
```ts
      input: {
        main: resolve(root, "src/main.ts"),
        kit: resolve(root, "src/kit.ts"),
      },
```

- [ ] **Step 6: Run the unit tests to verify they pass**

```powershell
npm --prefix frontend run build
python -m uv run pytest apps/kit config/tests -q
```
Expected: PASS.

- [ ] **Step 7: Write the e2e harness and the first browser test**

`tests/e2e/__init__.py`: empty.

`tests/e2e/conftest.py`:
```python
import pytest
from playwright.sync_api import ConsoleMessage, Page


@pytest.fixture(autouse=True)
def _e2e_db(transactional_db):
    """The live server answers from another thread, so tests need a real (transactional) database."""


@pytest.fixture
def console_errors(page: Page) -> list[str]:
    """Console errors and uncaught exceptions, including CSP violations. Request it before page.goto()."""
    errors: list[str] = []

    def on_console(message: ConsoleMessage) -> None:
        if message.type == "error":
            errors.append(message.text)

    page.on("console", on_console)
    page.on("pageerror", lambda error: errors.append(str(error)))
    return errors
```

`tests/e2e/test_kit.py`:
```python
import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e

LOADED_FONTS = """async () => {
  await document.fonts.ready;
  return [...document.fonts]
    .filter((font) => font.status === "loaded")
    .map((font) => font.family.replaceAll('"', ""));
}"""


def test_kit_renders_under_an_enforced_csp(page: Page, live_server, vite_build, console_errors):
    response = page.goto(f"{live_server.url}/_kit/")
    assert response is not None
    assert response.ok
    assert "content-security-policy" in response.headers
    expect(page.get_by_role("heading", level=1)).to_have_text("Design kit")
    families = page.evaluate(LOADED_FONTS)
    assert "Inter" in families
    assert "Poppins" in families
    assert page.request.get(f"{live_server.url}/static/dist/icons.svg").ok
    assert console_errors == []
```

- [ ] **Step 8: Run the e2e test**

Run: `python -m uv run pytest -m e2e --ds=config.e2e_settings --browser chromium -q`
Expected: 1 passed. Then confirm the default run skips it: `python -m uv run pytest -n auto` reports the e2e test
as deselected, and everything else passes.

- [ ] **Step 9: CI job and docs**

Append to `.github/workflows/ci.yml` under `jobs:`:
```yaml
  e2e:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    services:
      postgres:
        image: postgres:17
        env:
          POSTGRES_USER: scholarsync
          POSTGRES_PASSWORD: scholarsync
          POSTGRES_DB: scholarsync
        ports: ["5432:5432"]
        options: >-
          --health-cmd "pg_isready -U scholarsync -d scholarsync"
          --health-interval 5s --health-timeout 5s --health-retries 10
    env:
      DJANGO_SECRET_KEY: ci-only-not-a-secret-0123456789abcdefghijklmnopqrstuvwxyz
      DATABASE_URL: postgres://scholarsync:scholarsync@localhost:5432/scholarsync
    steps:
      - uses: actions/checkout@v7
      - uses: astral-sh/setup-uv@v10.3.0  # no floating major tag is published; pin the full version
        with:
          enable-cache: true
      - uses: actions/setup-node@v7
        with:
          node-version: 22
          cache: npm
          cache-dependency-path: frontend/package-lock.json
      - run: uv sync --locked
      - run: npm --prefix frontend ci
      - run: npm --prefix frontend run build
      - run: uv run playwright install --with-deps chromium
      - run: uv run pytest -m e2e --ds=config.e2e_settings --browser chromium
```

`CLAUDE.md`:
- in the file structure, add `kit/             design kit + key-screen mockups at /_kit/ (no models; DJANGO_KIT)` after
  `office/`;
- add `e2e_settings.py (Playwright: HTTP live server, enforced CSP, kit on)` to the `config/` line;
- add `tests/e2e/` to the `tests/` line;
- in **Commands → Checks**, add, after the pytest command:
  `python -m uv run pytest -m e2e --ds=config.e2e_settings --browser chromium` (once:
  `python -m uv run playwright install chromium`).

`README.md`: in "Checks", add the same two lines. Under "Local development", add a line saying the design kit is at
`http://localhost:8000/_kit/` when `DJANGO_KIT=true` (the default with `DJANGO_DEBUG=true`).

- [ ] **Step 10: Full checks, then commit**

```powershell
python -m uv run ruff check .; python -m uv run ruff format --check .; python -m uv run mypy .
python -m uv run python manage.py makemigrations --check --dry-run
python -m uv run pytest -n auto
npm --prefix frontend run typecheck; npm --prefix frontend run check; npm --prefix frontend run budget
```
Expected: all clean.
```powershell
git add pyproject.toml uv.lock config/settings.py config/e2e_settings.py config/urls.py config/tests/test_settings.py .env.example apps/kit frontend/src/kit.ts frontend/src/styles/kit.css frontend/vite.config.ts tests/e2e .github/workflows/ci.yml CLAUDE.md README.md
git commit -m "feat: add dev-only design kit and Playwright e2e harness"
```

---

### Task 4: Controls (buttons, fields, file input, alerts)

**Files:**
- Create: `frontend/src/styles/components/buttons.css`, `forms.css`, `feedback.css`; modify `frontend/src/main.ts`
- Create: `templates/components/field.html`, `form_errors.html`, `file_input.html`
- Modify: `apps/core/templatetags/ui.py` (`field` tag)
- Create: `apps/kit/forms.py`, `apps/kit/templates/kit/sections/controls.html`
- Modify: `apps/kit/views.py` (`SECTIONS`, `index_context`)
- Test: `apps/core/tests/test_field_tag.py`; append to `apps/kit/tests/test_kit.py`

**Interfaces:**
- Consumes: `{% icon %}`, the tokens, `SECTIONS` / `index_context` (Task 3).
- Produces:
  - **Classes:** `.btn` + `.btn--primary|secondary|ghost|danger`, `.btn-row`, `.icon-btn`, `.spinner`,
    `.htmx-indicator`, `.input`, `.field` (+ `--invalid`, `--check`, `--group`), `.field__label|__required|__help|__error`,
    `.alert` + `.alert--success|warning|danger`, `.alert__title`.
  - **`{% field bound_field %}`:** help id `<auto_id>-help`, error id `<auto_id>-error`.
  - **`{% include "components/form_errors.html" with form=form %}`.**
  - **`{% include "components/file_input.html" with id name label help state progress filename error %}`,** where
    `state` is one of `idle`, `uploading`, `done`, `error`.
  - **`apps.kit.forms.KitForm`, `invalid_kit_form()`.**

- [ ] **Step 1: Write the failing tests**

`apps/core/tests/test_field_tag.py`:
```python
from django import forms
from django.template import Context, Template


class ApplicantForm(forms.Form):
    full_name = forms.CharField(label="Full name", help_text="As on your school ID.")
    school = forms.ChoiceField(label="School", choices=[("tcu", "Taguig City University")])
    nickname = forms.CharField(label="Nickname", required=False)
    year_level = forms.ChoiceField(
        label="Year level", widget=forms.RadioSelect, choices=[("1", "1st year"), ("2", "2nd year")]
    )
    consent = forms.BooleanField(label="I agree to the privacy notice")


def render_field(form: forms.Form, name: str) -> str:
    return Template("{% load ui %}{% field f %}").render(Context({"f": form[name]}))


def test_help_text_is_linked_to_the_input():
    html = render_field(ApplicantForm(), "full_name")
    assert '<p class="field__help" id="id_full_name-help">As on your school ID.</p>' in html
    assert 'aria-describedby="id_full_name-help"' in html
    assert "aria-invalid" not in html
    assert '<span class="field__required">(required)</span>' in html


def test_errors_mark_the_input_invalid_and_are_linked():
    form = ApplicantForm(data={"full_name": ""})
    form.is_valid()
    html = render_field(form, "full_name")
    assert 'aria-invalid="true"' in html
    assert 'aria-describedby="id_full_name-help id_full_name-error"' in html
    assert 'id="id_full_name-error"' in html
    assert "This field is required." in html
    assert "field--invalid" in html


def test_optional_fields_have_no_marker_or_description():
    html = render_field(ApplicantForm(), "nickname")
    assert "(required)" not in html
    assert "aria-describedby" not in html


def test_user_input_in_errors_is_escaped():
    form = ApplicantForm(data={"school": "<img src=x onerror=alert(1)>"})
    form.is_valid()
    html = render_field(form, "school")
    assert "<img" not in html
    assert "&lt;img src=x onerror=alert(1)&gt;" in html


def test_checkbox_puts_the_input_before_its_label():
    html = render_field(ApplicantForm(), "consent")
    assert "field--check" in html
    assert html.index('type="checkbox"') < html.index("<label")


def test_radio_group_is_a_fieldset_with_a_legend():
    html = render_field(ApplicantForm(), "year_level").strip()
    assert html.startswith('<fieldset class="field field--group')
    assert '<legend class="field__label">Year level' in html
```

Append to `apps/kit/tests/test_kit.py`:
```python
def test_kit_shows_controls_in_every_state(client, kit_on, vite_build):
    body = client.get("/_kit/").content.decode()
    assert '<section class="kit-section" id="controls"' in body
    for marker in ("btn--primary", "btn--secondary", "btn--ghost", "btn--danger", " disabled>"):
        assert marker in body
    assert 'aria-invalid="true"' in body
    assert '<div class="alert alert--danger" role="alert">' in body
    assert "<progress" in body
    assert "&lt;img src=x&gt;" in body  # echoed invalid choice, escaped
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m uv run pytest apps/core/tests/test_field_tag.py apps/kit -q`
Expected: FAIL. `Invalid block tag … 'field'`; no `controls` section.

- [ ] **Step 3: The `field` tag and component templates**

Add to `apps/core/templatetags/ui.py` (imports at the top):
```python
from django.forms import BoundField

GROUP_WIDGETS = {"radioselect", "checkboxselectmultiple"}


@register.inclusion_tag("components/field.html")
def field(bound_field: BoundField) -> dict[str, object]:
    """Label, help, error and widget for one form field, with the ARIA links between them."""
    help_id = f"{bound_field.auto_id}-help"
    error_id = f"{bound_field.auto_id}-error"
    described_by = [
        element_id
        for element_id, present in ((help_id, bound_field.help_text), (error_id, bound_field.errors))
        if present
    ]
    attrs: dict[str, str] = {}
    if described_by:
        attrs["aria-describedby"] = " ".join(described_by)
    if bound_field.errors:
        attrs["aria-invalid"] = "true"
    widget_type = bound_field.widget_type
    layout = (
        "check" if widget_type == "checkbox" else "group" if widget_type in GROUP_WIDGETS else "stacked"
    )
    return {
        "field": bound_field,
        "widget": bound_field.as_widget(attrs=attrs),
        "help_id": help_id,
        "error_id": error_id,
        "layout": layout,
    }
```

`templates/components/field.html`:
```django
{% load ui %}{% if layout == "group" %}
<fieldset class="field field--group{% if field.errors %} field--invalid{% endif %}">
  <legend class="field__label">{{ field.label }}{% if field.field.required %} <span class="field__required">(required)</span>{% endif %}</legend>
  {% if field.help_text %}<p class="field__help" id="{{ help_id }}">{{ field.help_text }}</p>{% endif %}
  {% if field.errors %}<p class="field__error" id="{{ error_id }}">{% icon "circle-alert" %}<span>{{ field.errors|join:" " }}</span></p>{% endif %}
  {{ widget }}
</fieldset>
{% elif layout == "check" %}
<div class="field field--check{% if field.errors %} field--invalid{% endif %}">
  {{ widget }}
  <label class="field__label" for="{{ field.id_for_label }}">{{ field.label }}</label>
  {% if field.help_text %}<p class="field__help" id="{{ help_id }}">{{ field.help_text }}</p>{% endif %}
  {% if field.errors %}<p class="field__error" id="{{ error_id }}">{% icon "circle-alert" %}<span>{{ field.errors|join:" " }}</span></p>{% endif %}
</div>
{% else %}
<div class="field{% if field.errors %} field--invalid{% endif %}">
  <label class="field__label" for="{{ field.id_for_label }}">{{ field.label }}{% if field.field.required %} <span class="field__required">(required)</span>{% endif %}</label>
  {% if field.help_text %}<p class="field__help" id="{{ help_id }}">{{ field.help_text }}</p>{% endif %}
  {% if field.errors %}<p class="field__error" id="{{ error_id }}">{% icon "circle-alert" %}<span>{{ field.errors|join:" " }}</span></p>{% endif %}
  {{ widget }}
</div>
{% endif %}
```

`templates/components/form_errors.html`:
```django
{% load ui %}{% if form.non_field_errors %}
<div class="alert alert--danger" role="alert">
  {% icon "circle-alert" %}
  <div>{% for error in form.non_field_errors %}<p>{{ error }}</p>{% endfor %}</div>
</div>
{% endif %}
```

`templates/components/file_input.html` (static states now; `upload.ts` drives them in M5):
```django
{% load ui %}
<div class="file-input{% if state == 'error' %} field--invalid{% endif %}">
  <label class="field__label" for="{{ id }}">{{ label }}</label>
  {% if help %}<p class="field__help" id="{{ id }}-help">{{ help }}</p>{% endif %}
  <input class="file-input__control" type="file" id="{{ id }}" name="{{ name }}" accept="application/pdf,image/jpeg,image/png"{% if help or state == 'error' %} aria-describedby="{% if help %}{{ id }}-help{% endif %}{% if help and state == 'error' %} {% endif %}{% if state == 'error' %}{{ id }}-error{% endif %}"{% endif %}{% if state == 'error' %} aria-invalid="true"{% endif %}>
  {% if state == "uploading" %}
  <div class="file-input__status">
    <progress max="100" value="{{ progress }}" aria-label="Upload progress for {{ label }}">{{ progress }}%</progress>
    <span>Uploading {{ filename }}: {{ progress }}%</span>
  </div>
  {% elif state == "done" %}
  <p class="file-input__status file-input__status--done">{% icon "circle-check" %}<span>{{ filename }} uploaded</span></p>
  {% elif state == "error" %}
  <p class="field__error" id="{{ id }}-error">{% icon "circle-alert" %}<span>{{ error }}</span></p>
  {% endif %}
</div>
```

- [ ] **Step 4: Component CSS**

`frontend/src/styles/components/buttons.css`:
```css
.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  min-height: var(--control-height);
  padding: 0 var(--space-5);
  border: 1px solid transparent;
  border-radius: var(--radius-md);
  font: 600 var(--text-base) / 1 var(--font-body);
  text-decoration: none;
  white-space: nowrap;
  cursor: pointer;
  transition:
    background-color var(--duration) var(--ease),
    border-color var(--duration) var(--ease);
}

.btn--primary {
  background: var(--brand-600);
  color: var(--text-inverse);
}

.btn--primary:hover {
  background: var(--brand-700);
  color: var(--text-inverse);
}

.btn--secondary {
  background: var(--surface);
  border-color: var(--border-control);
  color: var(--text);
}

.btn--secondary:hover {
  background: var(--surface-sunken);
  color: var(--text);
}

.btn--ghost {
  background: transparent;
  color: var(--link);
}

.btn--ghost:hover {
  background: var(--danger-50);
  color: var(--link-hover);
}

/* Outlined so a destructive action never looks like the red primary button (spec §12). */
.btn--danger {
  background: var(--surface);
  border-color: var(--danger);
  color: var(--danger);
}

.btn--danger:hover {
  background: var(--danger-50);
  color: var(--link-hover);
}

.btn:disabled,
.btn[aria-disabled="true"] {
  opacity: 0.55;
  cursor: not-allowed;
}

.btn-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-3);
}

.icon-btn {
  position: relative;
  display: inline-grid;
  place-items: center;
  width: var(--control-height);
  height: var(--control-height);
  padding: 0;
  border: 0;
  border-radius: var(--radius-md);
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
}

.icon-btn:hover {
  background: var(--surface-sunken);
  color: var(--text);
}

/* htmx adds .htmx-request to the element making a request (includeIndicatorStyles is off, spec §10). */
.htmx-indicator {
  display: none;
}

.htmx-request .htmx-indicator,
.htmx-request.htmx-indicator {
  display: inline-block;
}

.spinner {
  width: 1em;
  height: 1em;
  border: 2px solid currentColor;
  border-right-color: transparent;
  border-radius: var(--radius-full);
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(1turn);
  }
}
```

`frontend/src/styles/components/forms.css`:
```css
.field {
  display: grid;
  gap: var(--space-2);
  max-width: 40rem;
  margin: 0 0 var(--space-5);
}

fieldset.field {
  min-width: 0;
  padding: 0;
  border: 0;
}

.field__label {
  padding: 0;
  font-weight: 600;
}

.field__required {
  font-weight: 400;
  color: var(--text-muted);
}

.field__help {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--text-muted);
}

.field__error {
  display: flex;
  align-items: flex-start;
  gap: var(--space-2);
  margin: 0;
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--danger);
}

.input,
.field :is(input:not([type="checkbox"], [type="radio"], [type="file"]), select, textarea) {
  width: 100%;
  min-height: var(--control-height);
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--border-control);
  border-radius: var(--radius-md);
  background: var(--surface);
  color: var(--text);
  font: inherit;
}

.field textarea {
  min-height: 7rem;
  resize: vertical;
}

select.input,
.field select {
  appearance: none;
  padding-right: var(--space-10);
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%234b5563' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='m6 9 6 6 6-6'/%3E%3C/svg%3E");
  background-position: right var(--space-3) center;
  background-repeat: no-repeat;
  background-size: 1.25rem;
}

.input:focus-visible,
.field :is(input, select, textarea):focus-visible {
  outline: 3px solid var(--focus);
  outline-offset: 0;
  border-color: var(--focus);
}

.field--invalid :is(input:not([type="checkbox"], [type="radio"]), select, textarea) {
  border: 2px solid var(--danger);
}

.field :is(input[type="checkbox"], input[type="radio"]) {
  width: 1.25rem;
  height: 1.25rem;
  margin: 0.125rem 0 0;
  accent-color: var(--brand-600);
}

.field--check {
  grid-template-columns: auto 1fr;
  align-items: start;
  column-gap: var(--space-3);
}

.field--check > :not(input) {
  grid-column: 2;
}

.field--group label {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  min-height: var(--control-height);
}

.file-input {
  display: grid;
  gap: var(--space-2);
  max-width: 40rem;
  margin: 0 0 var(--space-5);
}

.file-input__control {
  min-height: var(--control-height);
  font: inherit;
}

.file-input__control::file-selector-button {
  min-height: var(--control-height);
  margin-right: var(--space-3);
  padding: 0 var(--space-4);
  border: 1px solid var(--border-control);
  border-radius: var(--radius-md);
  background: var(--surface);
  color: var(--text);
  font: 600 var(--text-sm) / 1 var(--font-body);
  cursor: pointer;
}

.file-input__status {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  margin: 0;
  font-size: var(--text-sm);
}

.file-input__status--done {
  color: var(--success);
}

progress {
  flex: 1;
  width: 100%;
  height: 0.5rem;
  border: 0;
  border-radius: var(--radius-full);
  background: var(--surface-sunken);
  appearance: none;
  overflow: hidden;
}

progress::-webkit-progress-bar {
  background: var(--surface-sunken);
}

progress::-webkit-progress-value {
  background: var(--info);
}

progress::-moz-progress-bar {
  background: var(--info);
}
```

`frontend/src/styles/components/feedback.css`:
```css
.alert {
  display: flex;
  align-items: flex-start;
  gap: var(--space-3);
  margin: 0 0 var(--space-5);
  padding: var(--space-4);
  border-left: 4px solid currentColor;
  border-radius: var(--radius-md);
  background: var(--info-50);
  color: var(--info);
}

.alert > .icon {
  margin-top: 0.125rem;
}

.alert p {
  margin: 0;
  color: var(--text);
}

.alert p + p {
  margin-top: var(--space-1);
}

.alert__title {
  font-weight: 600;
}

.alert--success {
  background: var(--success-50);
  color: var(--success);
}

.alert--warning {
  background: var(--warning-50);
  color: var(--warning);
}

.alert--danger {
  background: var(--danger-50);
  color: var(--danger);
}
```

`frontend/src/main.ts`: add after the `base.css` import:
```ts
import "./styles/components/buttons.css";
import "./styles/components/forms.css";
import "./styles/components/feedback.css";
```

- [ ] **Step 5: Kit form and the controls section**

`apps/kit/forms.py`:
```python
"""Sample forms for the design kit (no real data)."""

from django import forms

SCHOOLS = [
    ("", "Choose a school"),
    ("tcu", "Taguig City University"),
    ("pup", "Polytechnic University of the Philippines"),
    ("tup", "Technological University of the Philippines"),
]
YEAR_LEVELS = [("1", "1st year"), ("2", "2nd year"), ("3", "3rd year"), ("4", "4th year")]


class KitForm(forms.Form):
    full_name = forms.CharField(label="Full name", help_text="As it appears on your school ID.")
    email = forms.EmailField(label="Email address")
    school = forms.ChoiceField(label="School", choices=SCHOOLS)
    year_level = forms.ChoiceField(label="Year level", widget=forms.RadioSelect, choices=YEAR_LEVELS)
    notes = forms.CharField(label="Notes for the reviewer", widget=forms.Textarea, required=False)
    consent = forms.BooleanField(label="I agree to the privacy notice")


def invalid_kit_form() -> KitForm:
    form = KitForm(
        prefix="invalid",
        data={"invalid-full_name": "", "invalid-email": "not-an-email", "invalid-school": "<img src=x>"},
    )
    form.is_valid()
    form.add_error(None, "Check the highlighted fields, then submit again.")
    return form
```

`apps/kit/views.py`: add `("controls", "Controls")` to `SECTIONS`, add `from apps.kit.forms import KitForm,
invalid_kit_form`, and add two keys to the dict that `index_context` returns:
```python
        "empty_form": KitForm(prefix="empty"),
        "invalid_form": invalid_kit_form(),
```

`apps/kit/templates/kit/sections/controls.html`:
```django
{% load ui %}
<section class="kit-section" id="controls" aria-labelledby="controls-title">
  <h2 id="controls-title">Controls</h2>
  <div class="kit-state">
    <h3>Buttons</h3>
    <div class="btn-row">
      <button type="button" class="btn btn--primary">Submit application</button>
      <button type="button" class="btn btn--secondary">Save draft</button>
      <button type="button" class="btn btn--ghost">Cancel</button>
      <button type="button" class="btn btn--danger">{% icon "trash-2" %}Withdraw application</button>
    </div>
  </div>
  <div class="kit-state">
    <h3>Icons, disabled and busy</h3>
    <div class="btn-row">
      <a class="btn btn--secondary" href="#controls">{% icon "download" %}Export CSV</a>
      <button type="button" class="btn btn--primary" disabled>Submit application</button>
      <button type="button" class="btn btn--primary htmx-request" aria-busy="true"><span class="spinner htmx-indicator" aria-hidden="true"></span>Saving</button>
      <button type="button" class="icon-btn" aria-label="Edit profile">{% icon "pencil" %}</button>
    </div>
  </div>
  <div class="kit-state">
    <h3>Fields</h3>
    {% field empty_form.full_name %}
    {% field empty_form.email %}
    {% field empty_form.school %}
    {% field empty_form.year_level %}
    {% field empty_form.notes %}
    {% field empty_form.consent %}
  </div>
  <div class="kit-state">
    <h3>Fields with errors</h3>
    {% include "components/form_errors.html" with form=invalid_form %}
    {% field invalid_form.full_name %}
    {% field invalid_form.email %}
    {% field invalid_form.school %}
    {% field invalid_form.year_level %}
    {% field invalid_form.consent %}
  </div>
  <div class="kit-state">
    <h3>File input</h3>
    {% include "components/file_input.html" with id="file-idle" name="grades" label="Certificate of grades" help="PDF, JPG or PNG, up to 10 MB." state="idle" %}
    {% include "components/file_input.html" with id="file-uploading" name="residency" label="Proof of residency" state="uploading" progress=40 filename="barangay-certificate.pdf" %}
    {% include "components/file_input.html" with id="file-done" name="enrollment" label="Certificate of enrollment" state="done" filename="enrollment-2026.pdf" %}
    {% include "components/file_input.html" with id="file-error" name="valid-id" label="Valid ID" help="PDF, JPG or PNG, up to 10 MB." state="error" error="This file is 14 MB. Upload a file of 10 MB or less." %}
  </div>
  <div class="kit-state">
    <h3>Alerts</h3>
    <div class="alert" role="status">{% icon "info" %}<div><p class="alert__title">Applications open on 3 November</p><p>You can finish your profile now.</p></div></div>
    <div class="alert alert--success" role="status">{% icon "circle-check" %}<div><p>Your profile is complete.</p></div></div>
    <div class="alert alert--warning" role="status">{% icon "triangle-alert" %}<div><p class="alert__title">Your application was returned</p><p>Upload a clearer copy of your certificate of grades by 7 November 2026.</p></div></div>
    <div class="alert alert--danger" role="alert">{% icon "circle-alert" %}<div><p>We couldn't save your changes. Check your connection and try again.</p></div></div>
  </div>
</section>
```

- [ ] **Step 6: Build and run the tests to verify they pass**

```powershell
npm --prefix frontend run build
python -m uv run pytest apps/core apps/kit tests/test_icons.py tests/test_tokens.py -q
python -m uv run mypy .; npm --prefix frontend run check; npm --prefix frontend run budget
```
Expected: PASS; clean.

- [ ] **Step 7: Commit**

```powershell
git add frontend/src/main.ts frontend/src/styles/components templates/components apps/core/templatetags/ui.py apps/core/tests/test_field_tag.py apps/kit
git commit -m "feat: add button, field, file input and alert components"
```

---

### Task 5: Data display (table, sorting, pagination, stats, pills, cards, tabs, breadcrumbs, empty state)

**Files:**
- Create: `frontend/src/styles/components/data.css`; modify `frontend/src/main.ts`
- Create: `templates/components/pagination.html`, `stat_tile.html`, `empty_state.html`, `breadcrumbs.html`, `tabs.html`
- Modify: `apps/core/templatetags/ui.py` (`sort_th`, `pagination`)
- Create: `apps/kit/samples.py`, `apps/kit/templates/kit/sections/data.html`
- Modify: `apps/kit/views.py`
- Test: `apps/core/tests/test_table_tags.py`; append to `apps/kit/tests/test_kit.py`

**Interfaces:**
- Consumes: `.btn`, `.input`, `.field`, `{% icon %}`, `peso`.
- Produces:
  - **`{% sort_th "Label" "key" ["css class"] %}`** (needs `request` in the context). The current sort comes from
    `?sort=key` / `?sort=-key`. It drops `page` and keeps other query params.
  - **`{% pagination page_obj %}`.**
  - **Includes:** `stat_tile.html` (`label value icon tone hint`), `empty_state.html`
    (`icon title body action_url action_label`), `breadcrumbs.html` (`crumbs`: list of `{label, url}`; last =
    current), `tabs.html` (`tabs`: list of `{label, url, current, count}`).
  - **Classes:** `.table-wrap`, `.table`, `.sort`, `.table-count`, `.filters`, `.stats`, `.stat` (+ tones
    `brand|info|success|warning`), `.pill` (+ `--success|warning|danger|info|neutral`), `.card`, `.card__header`,
    `.card__title`, `.tabs`, `.breadcrumbs`, `.empty`, `.details`, `.meter-row`, `.steps`, `.timeline`, `.list`,
    `.checklist`.
  - **`apps.kit.samples`:** `Scholar` (TypedDict), `STATUSES`, `scholars() -> list[Scholar]`.
  - **`apps.kit.views.filtered_scholars(params: QueryDict) -> list[Scholar]`.**

- [ ] **Step 1: Write the failing tests**

`apps/core/tests/test_table_tags.py`:
```python
from html import unescape

from django.core.paginator import Paginator
from django.template import RequestContext, Template
from django.test import RequestFactory


def render(source: str, url: str, **context) -> str:
    request = RequestFactory().get(url)
    return Template("{% load ui %}" + source).render(RequestContext(request, context))


def test_sort_th_marks_the_current_column_and_flips_it():
    html = render('{% sort_th "Name" "name" %}', "/x/?sort=name&page=3&q=ana")
    assert 'aria-sort="ascending"' in html
    assert 'href="?sort=-name&amp;q=ana"' in html
    assert "#arrow-up" in html


def test_sort_th_descending():
    html = render('{% sort_th "Name" "name" %}', "/x/?sort=-name")
    assert 'aria-sort="descending"' in html
    assert 'href="?sort=name"' in html
    assert "#arrow-down" in html


def test_sort_th_other_columns_are_unsorted():
    html = render('{% sort_th "School" "school" %}', "/x/?sort=name&q=ana")
    assert html.startswith('<th scope="col">')
    assert "aria-sort" not in html
    assert 'href="?sort=school&amp;q=ana"' in html
    assert "#chevrons-up-down" in html


def test_sort_th_numeric_column():
    html = render('{% sort_th "Allowance" "amount" "num" %}', "/x/")
    assert html.startswith('<th scope="col" class="num">')


def test_sort_th_escapes_label_and_query():
    html = render('{% sort_th label "name" %}', '/x/?q="><script>', label="<b>Name</b>")
    assert "<script>" not in html
    assert "<b>" not in html
    assert "&lt;b&gt;Name&lt;/b&gt;" in html


def test_pagination_keeps_filters_and_links_neighbours():
    page = Paginator(range(100), 10).page(2)
    html = render("{% pagination page %}", "/x/?status=active&page=2", page=page)
    assert 'aria-label="Pagination"' in html
    assert "Page 2 of 10" in html
    assert 'href="?status=active&page=1"' in unescape(html)
    assert 'href="?status=active&page=3"' in unescape(html)


def test_pagination_is_empty_for_a_single_page():
    page = Paginator(range(3), 10).page(1)
    assert render("{% pagination page %}", "/x/", page=page).strip() == ""
```

Append to `apps/kit/tests/test_kit.py`:
```python
def test_kit_shows_data_components(client, kit_on, vite_build):
    body = client.get("/_kit/").content.decode()
    assert '<section class="kit-section" id="data"' in body
    for marker in ('class="stat ', 'class="pill pill--', 'class="card"', 'class="tabs"',
                   'aria-label="Breadcrumb"', 'class="empty"', "<meter", 'class="steps"',
                   'class="timeline"', 'aria-sort="ascending"'):  # fmt: skip
        assert marker in body, marker


def test_kit_table_filters_sorts_and_survives_bad_input(client, kit_on, vite_build):
    body = client.get("/_kit/?q=shaw").content.decode()
    assert "David Shaw" in body
    assert "William Heath" not in body
    for query in ("?page=abc", "?page=999", "?sort=__class__", "?status=nope"):
        assert client.get(f"/_kit/{query}").status_code == 200
    empty = client.get("/_kit/?q=nobody-has-this-name").content.decode()
    assert "No scholars match these filters" in empty
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m uv run pytest apps/core/tests/test_table_tags.py apps/kit -q`
Expected: FAIL. `Invalid block tag … 'sort_th'`; no `data` section.

- [ ] **Step 3: The tags and component templates**

Add to `apps/core/templatetags/ui.py`:
```python
from django.core.paginator import Page
from django.template import Context

SORT_ICONS = {"ascending": "arrow-up", "descending": "arrow-down", "": "chevrons-up-down"}


@register.simple_tag(takes_context=True)
def sort_th(context: Context, label: str, key: str, css_class: str = "") -> SafeString:
    """A sortable column header: ?sort=key ascending, ?sort=-key descending (spec §12)."""
    request = context["request"]
    current = request.GET.get("sort", "")
    query = request.GET.copy()
    query.pop("page", None)
    if current == key:
        query["sort"], direction = f"-{key}", "ascending"
    elif current == f"-{key}":
        query["sort"], direction = key, "descending"
    else:
        query["sort"], direction = key, ""
    return format_html(
        '<th scope="col"{}{}><a class="sort" href="?{}">{}{}</a></th>',
        format_html(' class="{}"', css_class) if css_class else "",
        format_html(' aria-sort="{}"', direction) if direction else "",
        query.urlencode(),
        label,
        icon(SORT_ICONS[direction]),
    )


@register.inclusion_tag("components/pagination.html", takes_context=True)
def pagination(context: Context, page: Page[object]) -> dict[str, object]:
    return {"page": page, "request": context["request"]}
```

`templates/components/pagination.html`:
```django
{% load ui %}{% if page.paginator.num_pages > 1 %}
<nav class="pagination" aria-label="Pagination">
  {% if page.has_previous %}<a class="btn btn--secondary" href="{% querystring page=page.previous_page_number %}" rel="prev">{% icon "chevron-left" %}Previous</a>{% endif %}
  <p class="pagination__status">Page {{ page.number }} of {{ page.paginator.num_pages }}</p>
  {% if page.has_next %}<a class="btn btn--secondary" href="{% querystring page=page.next_page_number %}" rel="next">Next{% icon "chevron-right" %}</a>{% endif %}
</nav>
{% endif %}
```

`templates/components/stat_tile.html`:
```django
{% load ui %}
<div class="stat stat--{{ tone|default:'neutral' }}">
  <span class="stat__chip">{% icon icon %}</span>
  <div>
    <p class="stat__label">{{ label }}</p>
    <p class="stat__value num">{{ value }}</p>
    {% if hint %}<p class="stat__hint">{{ hint }}</p>{% endif %}
  </div>
</div>
```

`templates/components/empty_state.html`:
```django
{% load ui %}
<div class="empty">
  {% icon icon|default:"inbox" %}
  <p class="empty__title">{{ title }}</p>
  {% if body %}<p>{{ body }}</p>{% endif %}
  {% if action_url %}<a class="btn btn--secondary" href="{{ action_url }}">{{ action_label }}</a>{% endif %}
</div>
```

`templates/components/breadcrumbs.html`:
```django
<nav class="breadcrumbs" aria-label="Breadcrumb">
  <ol>
    {% for crumb in crumbs %}
    <li>{% if forloop.last %}<span aria-current="page">{{ crumb.label }}</span>{% else %}<a href="{{ crumb.url }}">{{ crumb.label }}</a>{% endif %}</li>
    {% endfor %}
  </ol>
</nav>
```

`templates/components/tabs.html`:
```django
<nav class="tabs" aria-label="{{ tabs_label|default:'Sections' }}">
  {% for tab in tabs %}<a href="{{ tab.url }}"{% if tab.current %} aria-current="page"{% endif %}>{{ tab.label }}{% if tab.count %}<span class="tabs__count">{{ tab.count }}</span>{% endif %}</a>{% endfor %}
</nav>
```

- [ ] **Step 4: Data CSS**

`frontend/src/styles/components/data.css`:
```css
.card {
  padding: var(--space-6);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface);
}

.card__header {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--space-2) var(--space-4);
  margin-bottom: var(--space-4);
}

.card__title {
  margin: 0;
  font-size: var(--text-lg);
}

.stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(14rem, 1fr));
  gap: var(--space-4);
  margin-bottom: var(--space-6);
}

.stat {
  display: flex;
  align-items: flex-start;
  gap: var(--space-4);
  padding: var(--space-5);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface);
}

.stat__chip {
  display: grid;
  flex: none;
  place-items: center;
  width: 2.75rem;
  height: 2.75rem;
  border-radius: var(--radius-md);
  background: var(--surface-sunken);
  color: var(--text-muted);
}

.stat--brand .stat__chip {
  background: var(--brand-50);
  color: var(--brand-600);
}

.stat--info .stat__chip {
  background: var(--info-50);
  color: var(--info);
}

.stat--success .stat__chip {
  background: var(--success-50);
  color: var(--success);
}

.stat--warning .stat__chip {
  background: var(--warning-50);
  color: var(--warning);
}

.stat__label,
.stat__hint {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--text-muted);
}

.stat__value {
  margin: 0;
  font-family: var(--font-heading);
  font-size: var(--text-2xl);
  font-weight: 600;
  line-height: var(--leading-tight);
}

.pill {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  padding: 0.125rem var(--space-3) 0.125rem var(--space-2);
  border-radius: var(--radius-full);
  background: var(--gray-100);
  color: var(--gray-700);
  font-size: var(--text-sm);
  font-weight: 500;
  white-space: nowrap;
}

.pill .icon {
  width: 1rem;
  height: 1rem;
}

.pill--success {
  background: var(--success-50);
  color: var(--success);
}

.pill--warning {
  background: var(--warning-50);
  color: var(--warning);
}

.pill--danger {
  background: var(--danger-50);
  color: var(--danger);
}

.pill--info {
  background: var(--info-50);
  color: var(--info);
}

.filters {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: var(--space-3);
  margin-bottom: var(--space-4);
}

.filters .field {
  flex: 1 1 12rem;
  margin: 0;
}

.table-count {
  margin: 0 0 var(--space-2);
  font-size: var(--text-sm);
  color: var(--text-muted);
}

.table-wrap {
  overflow-x: auto;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface);
}

.table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--text-sm);
}

.table :is(th, td) {
  padding: var(--space-3) var(--space-4);
  border-bottom: 1px solid var(--border);
  text-align: left;
  vertical-align: middle;
}

.table thead th {
  background: var(--surface-sunken);
  color: var(--text-muted);
  font-weight: 600;
  white-space: nowrap;
}

.table tbody th {
  font-weight: 500;
}

.table tbody tr:last-child :is(th, td) {
  border-bottom: 0;
}

.table tbody tr:hover {
  background: var(--bg);
}

.table .num {
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.table .select {
  width: 3rem;
}

.table input[type="checkbox"] {
  width: 1.25rem;
  height: 1.25rem;
  accent-color: var(--brand-600);
}

.sort {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  color: inherit;
  text-decoration: none;
}

.sort .icon {
  width: 1rem;
  height: 1rem;
}

[aria-sort] .sort {
  color: var(--text);
}

.pagination {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-3);
  margin-top: var(--space-4);
}

.pagination__status {
  margin: 0;
  color: var(--text-muted);
}

.tabs {
  display: flex;
  gap: var(--space-1);
  margin-bottom: var(--space-6);
  border-bottom: 1px solid var(--border);
  overflow-x: auto;
}

.tabs a {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  min-height: var(--control-height);
  margin-bottom: -1px;
  padding: 0 var(--space-4);
  border-bottom: 3px solid transparent;
  color: var(--text-muted);
  font-weight: 500;
  text-decoration: none;
  white-space: nowrap;
}

.tabs a:hover {
  color: var(--text);
}

.tabs a[aria-current="page"] {
  border-bottom-color: var(--brand-600);
  color: var(--text);
}

.tabs__count {
  padding: 0 var(--space-2);
  border-radius: var(--radius-full);
  background: var(--surface-sunken);
  font-size: var(--text-sm);
}

.breadcrumbs ol {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  margin: 0 0 var(--space-4);
  padding: 0;
  list-style: none;
  font-size: var(--text-sm);
  color: var(--text-muted);
}

.breadcrumbs li + li::before {
  content: "/" / "";
  margin-right: var(--space-2);
}

.empty {
  display: grid;
  justify-items: center;
  gap: var(--space-3);
  padding: var(--space-12) var(--space-6);
  border: 1px dashed var(--border-control);
  border-radius: var(--radius-lg);
  color: var(--text-muted);
  text-align: center;
}

.empty > .icon {
  width: 2.5rem;
  height: 2.5rem;
}

.empty p {
  margin: 0;
}

.empty__title {
  color: var(--text);
  font-size: var(--text-lg);
  font-weight: 600;
}

.details {
  display: grid;
  grid-template-columns: minmax(8rem, 14rem) 1fr;
  gap: var(--space-3) var(--space-6);
  margin: 0;
}

.details dt {
  color: var(--text-muted);
}

.details dd {
  margin: 0;
}

@media (max-width: 40rem) {
  .details {
    grid-template-columns: 1fr;
    row-gap: var(--space-1);
  }

  .details dd {
    margin-bottom: var(--space-3);
  }
}

meter {
  width: 100%;
  height: 0.75rem;
}

.meter-row {
  display: grid;
  gap: var(--space-1);
}

.meter-row p {
  margin: 0;
  font-size: var(--text-sm);
}

.steps {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3) var(--space-6);
  margin: 0 0 var(--space-6);
  padding: 0;
  list-style: none;
}

.steps__item {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  color: var(--text-muted);
  font-weight: 500;
}

.steps__marker {
  display: grid;
  place-items: center;
  width: 1.75rem;
  height: 1.75rem;
  border: 2px solid var(--border-control);
  border-radius: var(--radius-full);
  font-size: var(--text-sm);
}

.steps__marker .icon {
  width: 1rem;
  height: 1rem;
}

.steps__item--done {
  color: var(--success);
}

.steps__item--done .steps__marker {
  border-color: var(--success);
  background: var(--success-50);
}

.steps__item--current {
  color: var(--text);
}

.steps__item--current .steps__marker {
  border-color: var(--brand-600);
  background: var(--brand-600);
  color: var(--text-inverse);
}

.timeline {
  margin: 0;
  padding: 0;
  border-left: 2px solid var(--border);
  list-style: none;
}

.timeline li {
  position: relative;
  padding: 0 0 var(--space-5) var(--space-5);
}

.timeline li::before {
  content: "";
  position: absolute;
  top: 0.45rem;
  left: -5px;
  width: 8px;
  height: 8px;
  border-radius: var(--radius-full);
  background: var(--gray-400);
}

.timeline li:first-child::before {
  background: var(--brand-600);
}

.timeline p {
  margin: 0;
}

.timeline__what {
  font-weight: 600;
}

.timeline__when {
  font-size: var(--text-sm);
  color: var(--text-muted);
}

.list {
  margin: 0;
  padding: 0;
  list-style: none;
}

.list > li {
  padding-block: var(--space-3);
  border-top: 1px solid var(--border);
}

.list > li:first-child {
  padding-top: 0;
  border-top: 0;
}

.list p {
  margin: 0;
}

.checklist {
  display: grid;
  gap: var(--space-3);
  margin: 0 0 var(--space-4);
  padding: 0;
  list-style: none;
}

.checklist li {
  display: flex;
  align-items: flex-start;
  gap: var(--space-3);
}

.checklist p {
  margin: 0;
}

.checklist .is-met > .icon {
  color: var(--success);
}

.checklist .is-unmet > .icon {
  color: var(--danger);
}

.checklist .is-pending > .icon {
  color: var(--text-muted);
}
```

In `frontend/src/main.ts`, add after the `feedback.css` import: `import "./styles/components/data.css";`

- [ ] **Step 5: Sample data and the data section**

`apps/kit/samples.py`:
```python
"""Sample data for the design kit and mockups.

Names are Faker en_PH output (Faker.seed(2026)), never real people. Amounts and rules are placeholders
until Kenneth confirms them (spec §18, open questions 2–5).
"""

from decimal import Decimal
from typing import TypedDict


class Status(TypedDict):
    label: str
    tone: str
    icon: str


class Scholar(TypedDict):
    id: int
    name: str
    school: str
    tier: str
    amount: Decimal
    status: str
    status_label: str
    tone: str
    icon: str


NAMES = [
    "David Shaw", "William Heath", "Curtis Walker", "Carolyn Hawkins", "Krista Kelley",
    "Jessica Tate", "Karen Willis", "John Mendez", "Daniel Montoya", "Shannon Briggs",
    "Gina Shelton", "Jason King",
]  # fmt: skip
SCHOOLS = [
    "Taguig City University",
    "University of Makati",
    "Polytechnic University of the Philippines",
    "Technological University of the Philippines",
]
TIERS = [
    ("Basic", Decimal("5000.00")),
    ("Priority", Decimal("7500.00")),
    ("Honors", Decimal("10000.00")),
]
STATUSES: dict[str, Status] = {
    "active": {"label": "Active", "tone": "success", "icon": "circle-check"},
    "at_risk": {"label": "At risk", "tone": "warning", "icon": "triangle-alert"},
    "on_hold": {"label": "On hold", "tone": "neutral", "icon": "info"},
    "ended": {"label": "Ended", "tone": "danger", "icon": "circle-alert"},
}
_SCHOLAR_STATUSES = [
    "active", "active", "at_risk", "active", "on_hold", "active",
    "ended", "active", "at_risk", "active", "active", "on_hold",
]  # fmt: skip


def scholars() -> list[Scholar]:
    rows: list[Scholar] = []
    for index, (name, status) in enumerate(zip(NAMES, _SCHOLAR_STATUSES, strict=True)):
        tier, amount = TIERS[index % len(TIERS)]
        info = STATUSES[status]
        rows.append(
            {
                "id": index + 1,
                "name": name,
                "school": SCHOOLS[index % len(SCHOOLS)],
                "tier": tier,
                "amount": amount,
                "status": status,
                "status_label": info["label"],
                "tone": info["tone"],
                "icon": info["icon"],
            }
        )
    return rows
```

In `apps/kit/views.py`:
- add `("data", "Data display")` to `SECTIONS`;
- add these imports: `from typing import Any`, `from django.core.paginator import Paginator`,
  `from django.http import QueryDict`, `from django.urls import reverse`, `from apps.kit import samples`;
- add `filtered_scholars` and replace `index_context` with the version below:
```python
SORTS: dict[str, Callable[[samples.Scholar], Any]] = {
    "name": lambda row: row["name"],
    "school": lambda row: row["school"],
    "amount": lambda row: row["amount"],
}


def filtered_scholars(params: QueryDict) -> list[samples.Scholar]:
    """Filter and sort the sample rows. Unknown statuses and sort keys are ignored, never errors."""
    rows = samples.scholars()
    query = params.get("q", "").strip().casefold()
    if query:
        rows = [row for row in rows if query in row["name"].casefold()]
    status = params.get("status", "")
    if status in samples.STATUSES:
        rows = [row for row in rows if row["status"] == status]
    sort = params.get("sort", "name")
    if key := SORTS.get(sort.removeprefix("-")):
        rows.sort(key=key, reverse=sort.startswith("-"))
    return rows


def index_context(request: HttpRequest) -> dict[str, object]:
    rows = filtered_scholars(request.GET)
    return {
        "sections": [
            {"id": key, "title": title, "template": f"kit/sections/{key}.html"}
            for key, title in SECTIONS
        ],
        "swatches": SWATCHES,
        "icons": icon_names(),
        "empty_form": KitForm(prefix="empty"),
        "invalid_form": invalid_kit_form(),
        # get_page() turns ?page=abc or ?page=999 into a valid page instead of an error.
        "scholars": Paginator(rows, 5).get_page(request.GET.get("page")),
        "total": len(rows),
        "statuses": samples.STATUSES,
        "clear_url": f"{reverse('kit:index')}#data",
        "crumbs": [{"label": "Scholars", "url": "#data"}, {"label": "David Shaw", "url": ""}],
        "tabs": [
            {"label": "Overview", "url": "#data", "current": True, "count": 0},
            {"label": "Documents", "url": "#data", "current": False, "count": 4},
            {"label": "History", "url": "#data", "current": False, "count": 0},
        ],
    }
```

`apps/kit/templates/kit/sections/data.html`:
```django
{% load ui %}
<section class="kit-section" id="data" aria-labelledby="data-title">
  <h2 id="data-title">Data display</h2>
  <div class="kit-state">
    <h3>Filter bar, sortable table and pagination</h3>
    <form class="filters" method="get" action="{% url 'kit:index' %}#data" role="search" aria-label="Filter scholars">
      <div class="field"><label class="field__label" for="filter-q">Name</label><input class="input" type="search" id="filter-q" name="q" value="{{ request.GET.q }}"></div>
      <div class="field">
        <label class="field__label" for="filter-status">Status</label>
        <select class="input" id="filter-status" name="status">
          <option value="">Any status</option>
          {% for key, status in statuses.items %}<option value="{{ key }}"{% if request.GET.status == key %} selected{% endif %}>{{ status.label }}</option>{% endfor %}
        </select>
      </div>
      <button class="btn btn--secondary" type="submit">{% icon "filter" %}Apply filters</button>
    </form>
    <div id="scholars-table">
      <p class="table-count">{{ total }} scholar{{ total|pluralize }}</p>
      {% if scholars.object_list %}
      <div class="table-wrap" role="region" aria-labelledby="scholars-caption" tabindex="0">
        <table class="table">
          <caption id="scholars-caption" class="visually-hidden">Scholars</caption>
          <thead><tr>{% sort_th "Name" "name" %}{% sort_th "School" "school" %}<th scope="col">Tier</th>{% sort_th "Allowance" "amount" "num" %}<th scope="col">Status</th></tr></thead>
          <tbody>
            {% for scholar in scholars %}
            <tr>
              <th scope="row">{{ scholar.name }}</th>
              <td>{{ scholar.school }}</td>
              <td>{{ scholar.tier }}</td>
              <td class="num">{{ scholar.amount|peso }}</td>
              <td><span class="pill pill--{{ scholar.tone }}">{% icon scholar.icon %}{{ scholar.status_label }}</span></td>
            </tr>
            {% endfor %}
          </tbody>
        </table>
      </div>
      {% pagination scholars %}
      {% else %}
      {% include "components/empty_state.html" with icon="search" title="No scholars match these filters" body="Try another name or status." action_url=clear_url action_label="Clear filters" %}
      {% endif %}
    </div>
  </div>
  <div class="kit-state">
    <h3>Stat tiles</h3>
    <div class="stats">
      {% include "components/stat_tile.html" with label="Active scholars" value="1,284" icon="users" tone="brand" hint="38 more than last term" %}
      {% include "components/stat_tile.html" with label="Applications waiting" value="96" icon="file-text" tone="info" hint="12 waiting over 7 days" %}
      {% include "components/stat_tile.html" with label="Released this year" value="₱18,240,000.00" icon="banknote" tone="success" %}
      {% include "components/stat_tile.html" with label="At risk" value="23" icon="triangle-alert" tone="warning" hint="Below the renewal rule" %}
    </div>
  </div>
  <div class="kit-state">
    <h3>Status pills</h3>
    <div class="btn-row">
      <span class="pill pill--success">{% icon "circle-check" %}Approved</span>
      <span class="pill pill--info">{% icon "file-text" %}Under review</span>
      <span class="pill pill--warning">{% icon "triangle-alert" %}Returned</span>
      <span class="pill pill--danger">{% icon "circle-alert" %}Rejected</span>
      <span class="pill">{% icon "info" %}Draft</span>
    </div>
  </div>
  <div class="kit-state">
    <h3>Card, breadcrumbs, tabs and details</h3>
    {% include "components/breadcrumbs.html" %}
    {% include "components/tabs.html" with tabs_label="Scholar sections" %}
    <div class="card">
      <div class="card__header"><h4 class="card__title">TCU CEAA scholarship</h4><span class="pill pill--success">{% icon "circle-check" %}Active</span></div>
      <dl class="details">
        <dt>Tier</dt><dd>Priority</dd>
        <dt>Allowance per term</dt><dd class="num">₱7,500.00</dd>
        <dt>Started</dt><dd>1st semester, 2025–2026</dd>
      </dl>
    </div>
  </div>
  <div class="kit-state">
    <h3>Meter, steps and timeline</h3>
    <div class="meter-row">
      <label for="kit-budget">Budget used</label>
      <meter id="kit-budget" min="0" max="100" low="70" high="90" optimum="0" value="64">64%</meter>
      <p class="num">64% of ₱12,000,000.00</p>
    </div>
    <ol class="steps" aria-label="Application progress">
      <li class="steps__item steps__item--done"><span class="steps__marker">{% icon "check" %}</span>Profile<span class="visually-hidden"> (done)</span></li>
      <li class="steps__item steps__item--current" aria-current="step"><span class="steps__marker">2</span>Documents</li>
      <li class="steps__item"><span class="steps__marker">3</span>Review</li>
      <li class="steps__item"><span class="steps__marker">4</span>Submit</li>
    </ol>
    <ol class="timeline">
      <li><p class="timeline__what">Returned to the applicant</p><p class="timeline__when"><time datetime="2026-10-20T14:05+08:00">20 Oct 2026, 2:05 PM</time> by Krista Kelley</p></li>
      <li><p class="timeline__what">Submitted</p><p class="timeline__when"><time datetime="2026-10-02T09:14+08:00">2 Oct 2026, 9:14 AM</time> by the applicant</p></li>
    </ol>
  </div>
  <div class="kit-state">
    <h3>Empty state</h3>
    {% include "components/empty_state.html" with icon="inbox" title="No applications yet" body="Applications appear here as soon as students submit them." %}
  </div>
</section>
```

- [ ] **Step 6: Build and run the tests to verify they pass**

```powershell
npm --prefix frontend run build
python -m uv run pytest apps/core apps/kit tests -q
python -m uv run mypy .; npm --prefix frontend run check; npm --prefix frontend run budget
```
Expected: PASS; clean.

- [ ] **Step 7: Commit**

```powershell
git add frontend/src/main.ts frontend/src/styles/components/data.css templates/components apps/core/templatetags/ui.py apps/core/tests/test_table_tags.py apps/kit
git commit -m "feat: add table, pagination, stat, pill and navigation components"
```

---

### Task 6: htmx wiring, toasts and the filter-bar swap

**Files:**
- Modify: `frontend/package.json`, `frontend/package-lock.json` (`htmx.org` 2.0.11 as a dependency)
- Create: `frontend/src/toast.ts`; modify `frontend/src/main.ts`, `frontend/src/styles/components/feedback.css`
- Modify: `pyproject.toml`, `uv.lock` (`django-htmx`, `django-template-partials`), `config/settings.py`
- Create: `apps/core/htmx.py`, `templates/components/toast.html`
- Modify: `templates/base.html`
- Modify: `apps/kit/views.py`, `apps/kit/urls.py`, `kit/sections/data.html`; create `kit/sections/feedback.html`
- Test: `apps/core/tests/test_htmx.py`, `apps/core/tests/test_base_template.py`; append to
  `apps/kit/tests/test_kit.py`; create `tests/e2e/test_feedback.py`

**Interfaces:**
- Consumes: the `.alert`, `.btn`, `.icon-btn` classes; the kit's `index_context`.
- Produces:
  - **Python helpers in `apps.core.htmx`:**
    - `Tone = Literal["info", "success", "warning", "danger"]`;
    - `toast(response, message: str, tone: Tone = "success") -> response`;
    - `close_dialog(response) -> response`;
    - `HtmxHttpRequest` (an `HttpRequest` with `.htmx: HtmxDetails`).
  - **Client events:** `toast` (`{message, tone}`) and `closeDialog`.
  - **`base.html`:** the `#toasts` live region, the `#toast-template` `<template>`, `hx-headers` with `X-CSRFToken`,
    and the `htmx-config` meta.
  - **Settings:** `MESSAGE_TAGS = {ERROR: "danger"}`.
  - **TypeScript:** `toast.ts` exports `initToasts()` and `showToast(detail)`.
  - **URL:** `kit:demo-toast` (`POST /_kit/demo/toast/`).

- [ ] **Step 1: Write the failing tests**

`apps/core/tests/test_htmx.py`:
```python
import json

from django.http import HttpResponse

from apps.core.htmx import close_dialog, toast


def test_toast_sets_an_hx_trigger_event():
    response = toast(HttpResponse(status=204), "Saved", "success")
    assert json.loads(response["HX-Trigger"]) == {"toast": {"message": "Saved", "tone": "success"}}


def test_toast_and_close_dialog_merge():
    response = close_dialog(toast(HttpResponse(status=204), "Released", "success"))
    assert json.loads(response["HX-Trigger"]) == {
        "toast": {"message": "Released", "tone": "success"},
        "closeDialog": {},
    }
```

`apps/core/tests/test_base_template.py`:
```python
import json
import re


def test_htmx_config_is_locked_down(client, vite_build):
    body = client.get("/").content.decode()
    config = json.loads(re.search(r"<meta name=\"htmx-config\" content='([^']+)'>", body).group(1))
    assert config == {
        "allowEval": False,
        "allowScriptTags": False,
        "includeIndicatorStyles": False,
        "selfRequestsOnly": True,
        "historyCacheSize": 0,
        "refreshOnHistoryMiss": True,
    }


def test_body_sends_the_csrf_token_with_htmx_requests(client, vite_build):
    body = client.get("/").content.decode()
    headers = json.loads(re.search(r"<body hx-headers='([^']+)'>", body).group(1))
    assert len(headers["X-CSRFToken"]) >= 32


def test_toast_region_and_template_exist(client, vite_build):
    body = client.get("/").content.decode()
    assert '<div id="toasts" class="toasts" role="status" aria-live="polite">' in body
    assert '<template id="toast-template">' in body
```

Append to `apps/kit/tests/test_kit.py`:
```python
def test_htmx_filter_returns_only_the_table_partial(client, kit_on, vite_build):
    response = client.get("/_kit/?q=shaw", headers={"HX-Request": "true", "HX-Target": "scholars-table"})
    body = response.content.decode()
    assert body.lstrip().startswith('<div id="scholars-table"')
    assert "<html" not in body
    assert "David Shaw" in body


def test_demo_toast_over_htmx_returns_204_with_a_trigger(client, kit_on):
    response = client.post(
        "/_kit/demo/toast/", {"message": "Saved", "tone": "warning"}, headers={"HX-Request": "true"}
    )
    assert response.status_code == 204
    assert json.loads(response["HX-Trigger"]) == {"toast": {"message": "Saved", "tone": "warning"}}


def test_demo_toast_without_htmx_uses_messages(client, kit_on, vite_build):
    response = client.post("/_kit/demo/toast/", {"message": "Saved", "tone": "danger"}, follow=True)
    body = response.content.decode()
    assert '<div class="toast toast--danger" data-toast data-tone="danger">' in body
    assert "Saved" in body


def test_demo_toast_rejects_unknown_tones(client, kit_on):
    response = client.post(
        "/_kit/demo/toast/", {"message": "x", "tone": "evil"}, headers={"HX-Request": "true"}
    )
    assert json.loads(response["HX-Trigger"])["toast"]["tone"] == "info"
```
Add `import json` to the top of `apps/kit/tests/test_kit.py`.

`tests/e2e/test_feedback.py`:
```python
import re

import pytest
from playwright.sync_api import Browser, Page, expect

pytestmark = pytest.mark.e2e

PAYLOAD = '<img src=x onerror="window.pwned=1">'


def test_htmx_toast_shows_text_not_markup(page: Page, live_server, vite_build, console_errors):
    page.goto(f"{live_server.url}/_kit/#feedback")
    page.get_by_label("Message", exact=True).fill(PAYLOAD)
    page.get_by_role("button", name="Show success").click()
    toast = page.locator("#toasts .toast")
    expect(toast).to_have_count(1)
    expect(toast).to_contain_text(PAYLOAD)
    expect(page.locator("#toasts img")).to_have_count(0)
    assert page.evaluate("window.pwned") is None
    assert console_errors == []


def test_success_toasts_hide_but_errors_stay(page: Page, live_server, vite_build):
    page.clock.install()
    page.goto(f"{live_server.url}/_kit/#feedback")
    page.get_by_role("button", name="Show success").click()
    page.get_by_role("button", name="Show error").click()
    expect(page.locator("#toasts .toast")).to_have_count(2)
    page.mouse.move(0, 0)
    page.clock.run_for(9000)
    expect(page.locator("#toasts .toast")).to_have_count(1)
    danger = page.locator("#toasts .toast--danger")
    expect(danger).to_be_visible()
    danger.get_by_role("button", name="Dismiss").click()
    expect(page.locator("#toasts .toast")).to_have_count(0)


def test_toast_without_javascript_comes_from_django_messages(browser: Browser, live_server, vite_build):
    context = browser.new_context(java_script_enabled=False)
    page = context.new_page()
    page.goto(f"{live_server.url}/_kit/#feedback")
    page.get_by_role("button", name="Show warning").click()
    expect(page.locator("#toasts .toast--warning")).to_contain_text("Application saved")
    context.close()


def test_filtering_swaps_only_the_table_and_keeps_history_out_of_storage(
    page: Page, live_server, vite_build, console_errors
):
    page.goto(f"{live_server.url}/_kit/")
    rows = page.locator("#scholars-table tbody tr")
    expect(rows).to_have_count(5)
    page.get_by_label("Name", exact=True).fill("shaw")
    expect(rows).to_have_count(1)
    expect(page).to_have_url(re.compile(r"q=shaw"))
    expect(page.locator("h1")).to_have_count(1)
    expect(page.locator("#scholars-table")).to_have_count(1)
    assert page.evaluate("window.localStorage.length") == 0
    assert console_errors == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m uv run pytest apps/core/tests/test_htmx.py apps/core/tests/test_base_template.py apps/kit -q`
Expected: FAIL. `ModuleNotFoundError: apps.core.htmx`; the base-template regexes find nothing; `/_kit/demo/toast/`
is 404.

- [ ] **Step 3: Install htmx and the Django packages**

```powershell
Push-Location frontend; npm install --save-exact htmx.org@2.0.11; Pop-Location
Select-String -Path frontend/package-lock.json -Pattern 'linux-x64-gnu' | Select-Object -First 1
python -m uv add "django-htmx>=1.29" "django-template-partials>=25.3"
```

In `config/settings.py`:
- add `"template_partials"` to `INSTALLED_APPS` (before `"apps.core"`). Its app config wraps the template loaders
  itself and removes `APP_DIRS`.
- add `"django_htmx.middleware.HtmxMiddleware"` to `MIDDLEWARE` right after
  `"django.contrib.auth.middleware.AuthenticationMiddleware"`.
- after `DEFAULT_AUTO_FIELD`:
```python
from django.contrib.messages import constants as message_constants  # noqa: E402

# Toast tones (templates/components/toast.html) use "danger", not Django's "error".
MESSAGE_TAGS = {message_constants.ERROR: "danger"}
```
- add `"django_htmx.*"` and `"template_partials.*"` to the mypy `ignore_missing_imports` override in
  `pyproject.toml` **only if** `mypy .` reports missing stubs for them (django-htmx ships `py.typed`).

- [ ] **Step 4: Server helpers, base template and the toast component**

`apps/core/htmx.py`:
```python
"""HTMX response helpers (spec §12): toasts and dialog closing travel in HX-Trigger."""

from typing import Literal

from django.http import HttpRequest, HttpResponse
from django_htmx.http import trigger_client_event
from django_htmx.middleware import HtmxDetails

Tone = Literal["info", "success", "warning", "danger"]


class HtmxHttpRequest(HttpRequest):
    htmx: HtmxDetails


def toast[R: HttpResponse](response: R, message: str, tone: Tone = "success") -> R:
    """toast.ts shows the message as text (never HTML) in the #toasts live region."""
    return trigger_client_event(response, "toast", {"message": message, "tone": tone})


def close_dialog[R: HttpResponse](response: R) -> R:
    """dialog.ts closes any open dialog."""
    return trigger_client_event(response, "closeDialog", {})
```

`templates/components/toast.html`:
```django
{% load ui %}<div class="toast toast--{{ tone }}" data-toast data-tone="{{ tone }}">
  <p class="toast__text">{{ text }}</p>
  <button type="button" class="icon-btn toast__close" data-toast-close aria-label="Dismiss">{% icon "x" %}</button>
</div>
```

`templates/base.html` (complete):
```django
{% load static django_vite %}<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="htmx-config" content='{"allowEval":false,"allowScriptTags":false,"includeIndicatorStyles":false,"selfRequestsOnly":true,"historyCacheSize":0,"refreshOnHistoryMiss":true}'>
  <title>{% block title %}ScholarSync{% endblock %} · City of Taguig</title>
  <link rel="icon" href="{% static 'images/favicon.svg' %}" type="image/svg+xml">
  <meta name="theme-color" content="#1b3366">
  {% vite_hmr_client %}
  {% vite_asset 'src/main.ts' %}
  {% block head %}{% endblock %}
</head>
<body hx-headers='{"X-CSRFToken": "{{ csrf_token }}"}'>
  <a class="skip-link" href="#main">Skip to content</a>
  {% block body %}
  <main id="main" tabindex="-1">
    {% block content %}{% endblock %}
  </main>
  {% endblock %}
  <div id="toasts" class="toasts" role="status" aria-live="polite">{% for message in messages %}{% include "components/toast.html" with tone=message.level_tag text=message.message %}{% endfor %}</div>
  <template id="toast-template">{% include "components/toast.html" with tone="info" text="" %}</template>
  {% block scripts %}{% endblock %}
</body>
</html>
```

- [ ] **Step 5: `toast.ts`, styles and `main.ts`**

`frontend/src/toast.ts`:
```ts
// Toasts (spec §12): the server sends HX-Trigger {"toast": {message, tone}} after an HTMX request,
// or a Django message after a normal POST (rendered into #toasts by base.html).
// Messages are set with textContent, never innerHTML. Success and info hide after 8 s unless
// hovered or focused; warnings and errors stay until dismissed.

export type Tone = "info" | "success" | "warning" | "danger";

export interface ToastDetail {
  message: string;
  tone?: Tone;
}

const TONES: ReadonlySet<string> = new Set(["info", "success", "warning", "danger"]);
const AUTO_HIDE_MS = 8000;

function isToastDetail(value: unknown): value is ToastDetail {
  return (
    typeof value === "object" &&
    value !== null &&
    typeof (value as { message?: unknown }).message === "string"
  );
}

function arm(toast: HTMLElement): void {
  const tone = toast.dataset.tone;
  if (tone !== "info" && tone !== "success") return;
  const tick = (): void => {
    if (toast.matches(":hover, :focus-within")) {
      window.setTimeout(tick, AUTO_HIDE_MS);
    } else {
      toast.remove();
    }
  };
  window.setTimeout(tick, AUTO_HIDE_MS);
}

export function showToast(detail: ToastDetail): HTMLElement | null {
  const region = document.getElementById("toasts");
  const template = document.getElementById("toast-template");
  if (!(region && template instanceof HTMLTemplateElement)) return null;
  const toast = template.content.firstElementChild?.cloneNode(true);
  if (!(toast instanceof HTMLElement)) return null;
  const tone = detail.tone && TONES.has(detail.tone) ? detail.tone : "info";
  toast.className = `toast toast--${tone}`;
  toast.dataset.tone = tone;
  const text = toast.querySelector(".toast__text");
  if (text) text.textContent = detail.message;
  region.append(toast);
  arm(toast);
  return toast;
}

export function initToasts(): void {
  for (const toast of document.querySelectorAll<HTMLElement>("#toasts [data-toast]")) arm(toast);
  document.addEventListener("click", (event) => {
    const button = event.target instanceof Element ? event.target.closest("[data-toast-close]") : null;
    button?.closest("[data-toast]")?.remove();
  });
  document.addEventListener("toast", (event) => {
    const detail: unknown = (event as CustomEvent<unknown>).detail;
    if (isToastDetail(detail)) showToast(detail);
  });
}
```

Append to `frontend/src/styles/components/feedback.css`:
```css
.toasts {
  position: fixed;
  z-index: 50;
  inset-inline-end: var(--space-4);
  inset-block-end: var(--space-4);
  display: grid;
  gap: var(--space-2);
  width: min(24rem, calc(100vw - 2 * var(--space-4)));
}

.toast {
  display: flex;
  align-items: flex-start;
  gap: var(--space-2);
  padding: var(--space-1) var(--space-1) var(--space-1) var(--space-4);
  border-left: 4px solid var(--info);
  border-radius: var(--radius-md);
  background: var(--surface);
  box-shadow: var(--shadow-2);
  color: var(--text);
}

.toast__text {
  flex: 1;
  margin: 0;
  padding-block: var(--space-3);
}

.toast--success {
  border-left-color: var(--success);
}

.toast--warning {
  border-left-color: var(--warning);
}

.toast--danger {
  border-left-color: var(--danger);
}

html:not(.js) .toast__close {
  display: none;
}

@media (prefers-reduced-motion: no-preference) {
  .toasts .toast {
    animation: toast-in var(--duration) var(--ease);
  }
}

@keyframes toast-in {
  from {
    opacity: 0;
    transform: translateY(0.5rem);
  }
}
```

Add to `frontend/src/styles/kit.css`:
```css
.kit-toasts {
  display: grid;
  gap: var(--space-2);
  max-width: 24rem;
}
```

`frontend/src/main.ts` (complete):
```ts
import "./styles/fonts.css";
import "./styles/tokens.css";
import "./styles/base.css";
import "./styles/components/buttons.css";
import "./styles/components/forms.css";
import "./styles/components/feedback.css";
import "./styles/components/data.css";
import "htmx.org";
import { initToasts } from "./toast";

document.documentElement.classList.add("js");
initToasts();
```

- [ ] **Step 6: Kit endpoints, the partial and the feedback section**

In `apps/kit/views.py`:
- add imports: `from typing import cast`, `from django.contrib import messages`,
  `from django.shortcuts import redirect`, `from django.views.decorators.http import require_POST` and
  `from apps.core.htmx import HtmxHttpRequest, Tone, toast`;
- add `("feedback", "Feedback")` to `SECTIONS`;
- change `index`'s parameter type to `HtmxHttpRequest`;
- add the demo view:
```python
TONE_LEVELS: dict[str, int] = {
    "info": messages.INFO,
    "success": messages.SUCCESS,
    "warning": messages.WARNING,
    "danger": messages.ERROR,
}


@kit_only
@require_safe
def index(request: HtmxHttpRequest) -> HttpResponse:
    context = index_context(request)
    if request.htmx and request.htmx.target == "scholars-table":
        return render(request, "kit/sections/data.html#scholars_table", context)
    return render(request, "kit/index.html", context)


@kit_only
@require_POST
def demo_toast(request: HtmxHttpRequest) -> HttpResponse:
    message = request.POST.get("message", "").strip()[:200] or "Saved"
    tone = request.POST.get("tone", "")
    if tone not in TONE_LEVELS:
        tone = "info"
    if request.htmx:
        return toast(HttpResponse(status=204), message, cast(Tone, tone))
    messages.add_message(request, TONE_LEVELS[tone], message)
    return redirect(f"{reverse('kit:index')}#feedback")
```

`apps/kit/urls.py`: add `path("demo/toast/", views.demo_toast, name="demo-toast"),`.

In `kit/sections/data.html`:
- change the first line to `{% load ui partials %}`;
- give the filter `<form>` these extra attributes:
  `hx-get="{% url 'kit:index' %}" hx-target="#scholars-table" hx-swap="outerHTML" hx-push-url="true"
  hx-trigger="submit, input delay:300ms, change"`;
- wrap the `<div id="scholars-table">…</div>` block in `{% partialdef scholars_table inline %}` …
  `{% endpartialdef %}`;
- add `hx-boost="true" hx-target="#scholars-table" hx-swap="outerHTML" hx-push-url="true"` to
  `<div id="scholars-table">`, so the sort and pagination links swap only the table too.

`apps/kit/templates/kit/sections/feedback.html`:
```django
<section class="kit-section" id="feedback" aria-labelledby="feedback-title">
  <h2 id="feedback-title">Feedback</h2>
  <div class="kit-state">
    <h3>Toasts</h3>
    <p>After an HTMX request the server sends the toast in <code>HX-Trigger</code>; after a normal POST it sends a Django message. Success and info toasts hide after 8 seconds unless hovered or focused. Warnings and errors stay until dismissed.</p>
    <form method="post" action="{% url 'kit:demo-toast' %}" hx-post="{% url 'kit:demo-toast' %}" hx-swap="none">
      {% csrf_token %}
      <div class="field"><label class="field__label" for="toast-message">Message</label><input class="input" id="toast-message" name="message" value="Application saved" maxlength="200"></div>
      <div class="btn-row">
        <button class="btn btn--secondary" type="submit" name="tone" value="success">Show success</button>
        <button class="btn btn--secondary" type="submit" name="tone" value="info">Show info</button>
        <button class="btn btn--secondary" type="submit" name="tone" value="warning">Show warning</button>
        <button class="btn btn--secondary" type="submit" name="tone" value="danger">Show error</button>
      </div>
    </form>
  </div>
  <div class="kit-state">
    <h3>Toast styles</h3>
    <div class="kit-toasts">
      {% include "components/toast.html" with tone="success" text="Application submitted" %}
      {% include "components/toast.html" with tone="info" text="Draft saved" %}
      {% include "components/toast.html" with tone="warning" text="2 documents still need review" %}
      {% include "components/toast.html" with tone="danger" text="We couldn't release the batch. Try again." %}
    </div>
  </div>
</section>
```

- [ ] **Step 7: Build and run all the tests**

```powershell
npm --prefix frontend run build
python -m uv run pytest -n auto
python -m uv run pytest -m e2e --ds=config.e2e_settings --browser chromium
python -m uv run mypy .; npm --prefix frontend run typecheck; npm --prefix frontend run check; npm --prefix frontend run budget
```
Expected: all PASS; the budget is still under 100 KB (htmx adds about 16 KB gzipped).

- [ ] **Step 8: Commit**

```powershell
git add frontend/package.json frontend/package-lock.json frontend/src/toast.ts frontend/src/main.ts frontend/src/styles pyproject.toml uv.lock config/settings.py apps/core/htmx.py apps/core/tests/test_htmx.py apps/core/tests/test_base_template.py templates/base.html templates/components/toast.html apps/kit tests/e2e/test_feedback.py
git commit -m "feat: wire htmx with CSRF, locked-down config and toasts"
```

---

### Task 7: Dialogs and the bulk bar

**Files:**
- Create: `frontend/src/dialog.ts`, `frontend/src/bulk.ts`; modify `frontend/src/main.ts`
- Modify: `frontend/src/styles/components/feedback.css` (dialog), `frontend/src/styles/components/data.css`
  (bulk bar)
- Create: `templates/components/dialog.html`; modify `templates/base.html` (dialog shell)
- Create: `apps/kit/templates/kit/demo_dialog.html`, `kit/demo_dialog_fragment.html`,
  `kit/sections/overlays.html`
- Modify: `apps/kit/views.py`, `apps/kit/urls.py`
- Test: append to `apps/kit/tests/test_kit.py`; create `tests/e2e/test_overlays.py`

**Interfaces:**
- Consumes: `toast()`, `close_dialog()`, `HtmxHttpRequest`, the `peso` filter, `samples.scholars()`.
- Produces:
  - **Dialog pattern:** a link with `href` (the full page, for no-JS) plus `hx-get` (the fragment) and
    `hx-target="#app-dialog-body"`. The fragment template extends `components/dialog.html` (blocks `dialog_title` and
    `dialog_body`; the title has `id="app-dialog-title"`). `[data-dialog-close]` closes. The server closes the
    dialog with `close_dialog()`.
  - **Bulk pattern:** `<form data-bulk>` with `input[data-bulk-item]`, an optional `input[data-bulk-all]`, and a
    `[data-bulk-bar]` holding a `[data-bulk-count]`. The bar's buttons are disabled until something is selected.
  - **TypeScript:** `initDialogs()`, `initBulk()`.
  - **URLs:** `kit:demo-dialog` (GET/POST `/_kit/demo/dialog/`), `kit:demo-bulk` (POST `/_kit/demo/bulk/`).

- [ ] **Step 1: Write the failing tests**

Append to `apps/kit/tests/test_kit.py`:
```python
def test_base_layout_has_the_dialog_shell(client, kit_on, vite_build):
    body = client.get("/_kit/").content.decode()
    assert '<dialog id="app-dialog" class="dialog" aria-labelledby="app-dialog-title">' in body


def test_demo_dialog_is_a_page_without_htmx_and_a_fragment_with_it(client, kit_on, vite_build):
    page = client.get("/_kit/demo/dialog/").content.decode()
    assert "<h1>Release allowances</h1>" in page
    fragment = client.get("/_kit/demo/dialog/", headers={"HX-Request": "true"}).content.decode()
    assert '<h2 class="dialog__title" id="app-dialog-title">Release allowances</h2>' in fragment
    assert "<html" not in fragment
    assert "₱60,000.00" in fragment


def test_demo_dialog_post_closes_the_dialog_and_toasts(client, kit_on):
    response = client.post("/_kit/demo/dialog/", headers={"HX-Request": "true"})
    assert response.status_code == 204
    assert json.loads(response["HX-Trigger"]) == {
        "toast": {"message": "Released ₱60,000.00 to 12 scholars", "tone": "success"},
        "closeDialog": {},
    }


def test_demo_bulk_counts_only_known_rows(client, kit_on):
    response = client.post(
        "/_kit/demo/bulk/", {"ids": ["1", "2", "999"], "action": "approve"}, headers={"HX-Request": "true"}
    )
    assert json.loads(response["HX-Trigger"])["toast"] == {
        "message": "Approved 2 applications",
        "tone": "success",
    }
    nothing = client.post("/_kit/demo/bulk/", {"action": "approve"}, headers={"HX-Request": "true"})
    assert json.loads(nothing["HX-Trigger"])["toast"]["tone"] == "warning"
```

`tests/e2e/test_overlays.py`:
```python
import pytest
from playwright.sync_api import Browser, Page, expect

pytestmark = pytest.mark.e2e


def test_dialog_opens_and_returns_focus_on_escape(page: Page, live_server, vite_build, console_errors):
    page.goto(f"{live_server.url}/_kit/#overlays")
    opener = page.get_by_role("link", name="Release allowances")
    opener.click()
    dialog = page.get_by_role("dialog", name="Release allowances")
    expect(dialog).to_be_visible()
    page.keyboard.press("Escape")
    expect(dialog).to_be_hidden()
    expect(opener).to_be_focused()
    assert console_errors == []


def test_confirming_closes_the_dialog_and_toasts(page: Page, live_server, vite_build, console_errors):
    page.goto(f"{live_server.url}/_kit/#overlays")
    page.get_by_role("link", name="Release allowances").click()
    dialog = page.get_by_role("dialog", name="Release allowances")
    dialog.get_by_role("button", name="Release allowances").click()
    expect(dialog).to_be_hidden()
    expect(page.locator("#toasts .toast--success")).to_contain_text("Released ₱60,000.00 to 12 scholars")
    assert console_errors == []


def test_dialog_link_works_without_javascript(browser: Browser, live_server, vite_build):
    context = browser.new_context(java_script_enabled=False)
    page = context.new_page()
    page.goto(f"{live_server.url}/_kit/#overlays")
    page.get_by_role("link", name="Release allowances").click()
    expect(page.get_by_role("heading", level=1)).to_have_text("Release allowances")
    page.get_by_role("button", name="Release allowances").click()
    expect(page.locator("#toasts .toast--success")).to_contain_text("Released ₱60,000.00")
    context.close()


def test_bulk_bar_counts_the_selection(page: Page, live_server, vite_build, console_errors):
    page.goto(f"{live_server.url}/_kit/#overlays")
    bar = page.locator("[data-bulk-bar]")
    approve = bar.get_by_role("button", name="Approve selected")
    expect(approve).to_be_disabled()
    page.get_by_label("Select David Shaw").check()
    page.get_by_label("Select William Heath").check()
    expect(bar).to_contain_text("2 selected")
    select_all = page.get_by_label("Select all applications")
    assert select_all.evaluate("(el) => el.indeterminate") is True
    select_all.check()
    expect(bar).to_contain_text("4 selected")
    approve.click()
    expect(page.locator("#toasts .toast--success")).to_contain_text("Approved 4 applications")
    assert console_errors == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m uv run pytest apps/kit -q`
Expected: FAIL. There's no dialog shell, and `/_kit/demo/dialog/` and `/_kit/demo/bulk/` are 404.

- [ ] **Step 3: TypeScript**

`frontend/src/dialog.ts`:
```ts
// Modal dialogs (spec §12). An opener is a link to the full page (no-JS) with hx-get to a fragment and
// hx-target="#app-dialog-body"; after the swap the dialog opens. [data-dialog-close] closes the dialog it
// sits in, and the server can close it with HX-Trigger "closeDialog". Focus returns to the opener.

function openDialog(dialog: HTMLDialogElement): void {
  if (dialog.open) return;
  const previous = document.activeElement;
  dialog.addEventListener(
    "close",
    () => {
      if (dialog.id === "app-dialog") document.getElementById("app-dialog-body")?.replaceChildren();
      if (previous instanceof HTMLElement && previous.isConnected) previous.focus();
    },
    { once: true },
  );
  dialog.showModal();
}

export function initDialogs(): void {
  document.addEventListener("click", (event) => {
    const target = event.target instanceof Element ? event.target : null;
    const dialog = target?.closest("[data-dialog-close]")?.closest("dialog");
    if (dialog) {
      event.preventDefault();
      dialog.close();
    }
  });
  document.addEventListener("htmx:afterSwap", (event) => {
    const { target } = (event as CustomEvent<{ target: Element }>).detail;
    const dialog = target.closest("dialog");
    if (dialog) openDialog(dialog);
  });
  document.addEventListener("closeDialog", () => {
    for (const dialog of document.querySelectorAll<HTMLDialogElement>("dialog[open]")) dialog.close();
  });
}
```

`frontend/src/bulk.ts`:
```ts
// Row selection for bulk actions (spec §12): <form data-bulk> with [data-bulk-item] checkboxes, an optional
// [data-bulk-all] checkbox and a [data-bulk-bar] whose buttons need a selection. Without JS the form still
// posts whatever is checked.

function update(form: HTMLFormElement): void {
  const items = [...form.querySelectorAll<HTMLInputElement>("input[data-bulk-item]")];
  const selected = items.filter((item) => item.checked).length;
  const all = form.querySelector<HTMLInputElement>("input[data-bulk-all]");
  if (all) {
    all.checked = selected > 0 && selected === items.length;
    all.indeterminate = selected > 0 && selected < items.length;
  }
  const count = form.querySelector("[data-bulk-count]");
  if (count) count.textContent = selected === 0 ? "None selected" : `${selected} selected`;
  for (const button of form.querySelectorAll<HTMLButtonElement>("[data-bulk-bar] button")) {
    button.disabled = selected === 0;
  }
}

function updateAll(): void {
  for (const form of document.querySelectorAll<HTMLFormElement>("form[data-bulk]")) update(form);
}

export function initBulk(): void {
  updateAll();
  document.addEventListener("change", (event) => {
    const input = event.target;
    if (!(input instanceof HTMLInputElement)) return;
    const form = input.closest<HTMLFormElement>("form[data-bulk]");
    if (!form) return;
    if (input.matches("[data-bulk-all]")) {
      for (const item of form.querySelectorAll<HTMLInputElement>("input[data-bulk-item]")) {
        item.checked = input.checked;
      }
    }
    update(form);
  });
  document.addEventListener("htmx:afterSettle", updateAll);
}
```

In `frontend/src/main.ts`, replace the named imports and the init calls with:
```ts
import { initBulk } from "./bulk";
import { initDialogs } from "./dialog";
import { initToasts } from "./toast";

document.documentElement.classList.add("js");
initToasts();
initDialogs();
initBulk();
```

- [ ] **Step 4: Styles, shell and templates**

Append to `frontend/src/styles/components/feedback.css`:
```css
.dialog {
  width: min(32rem, calc(100vw - 2 * var(--space-4)));
  padding: 0;
  border: 0;
  border-radius: var(--radius-lg);
  background: var(--surface);
  box-shadow: var(--shadow-2);
  color: var(--text);
}

.dialog::backdrop {
  background: rgb(17 24 39 / 0.5);
}

.dialog__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-4);
  padding: var(--space-4) var(--space-4) 0 var(--space-6);
}

.dialog__title {
  margin: 0;
  font-size: var(--text-xl);
}

.dialog__body {
  padding: var(--space-4) var(--space-6) var(--space-6);
}
```

Append to `frontend/src/styles/components/data.css`:
```css
.bulk-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  margin-bottom: var(--space-3);
  padding: var(--space-3) var(--space-4);
  border-radius: var(--radius-md);
  background: var(--info-50);
}

.bulk-bar__count {
  margin: 0;
  color: var(--info);
  font-weight: 600;
}

html:not(.js) [data-bulk-all] {
  visibility: hidden;
}
```

`templates/components/dialog.html`:
```django
{% load ui %}<div class="dialog__header">
  <h2 class="dialog__title" id="app-dialog-title">{% block dialog_title %}{% endblock %}</h2>
  <button type="button" class="icon-btn" data-dialog-close aria-label="Close">{% icon "x" %}</button>
</div>
<div class="dialog__body">{% block dialog_body %}{% endblock %}</div>
```

In `templates/base.html`, add after the `<template id="toast-template">…</template>` line:
```django
  <dialog id="app-dialog" class="dialog" aria-labelledby="app-dialog-title"><div id="app-dialog-body"></div></dialog>
```

`apps/kit/templates/kit/demo_dialog.html`:
```django
{% extends "kit/base.html" %}{% load ui partials %}
{% block title %}Release allowances{% endblock %}
{% block content %}
<h1>Release allowances</h1>
{% partialdef confirm inline %}
<form method="post" action="{% url 'kit:demo-dialog' %}" hx-post="{% url 'kit:demo-dialog' %}" hx-swap="none" hx-disabled-elt="find button[type='submit']">
  {% csrf_token %}
  <p>Release <strong class="num">{{ amount|peso }}</strong> to <strong>{{ count }} scholars</strong> for the 1st semester, 2026–2027? Only a program head can revert a release.</p>
  <div class="btn-row">
    <button type="submit" class="btn btn--primary">Release allowances</button>
    <a class="btn btn--ghost" href="{% url 'kit:index' %}#overlays" data-dialog-close>Cancel</a>
  </div>
</form>
{% endpartialdef %}
{% endblock %}
```

`apps/kit/templates/kit/demo_dialog_fragment.html`:
```django
{% extends "components/dialog.html" %}
{% block dialog_title %}Release allowances{% endblock %}
{% block dialog_body %}{% include "kit/demo_dialog.html#confirm" %}{% endblock %}
```

`apps/kit/templates/kit/sections/overlays.html`:
```django
{% load ui %}
<section class="kit-section" id="overlays" aria-labelledby="overlays-title">
  <h2 id="overlays-title">Dialogs and bulk actions</h2>
  <div class="kit-state">
    <h3>Confirmation dialog</h3>
    <p>The button is a link to a full page, so it works without JavaScript; with htmx the same content opens in a dialog.</p>
    <a class="btn btn--primary" href="{% url 'kit:demo-dialog' %}" hx-get="{% url 'kit:demo-dialog' %}" hx-target="#app-dialog-body" hx-swap="innerHTML">{% icon "banknote" %}Release allowances</a>
  </div>
  <div class="kit-state">
    <h3>Row selection and bulk bar</h3>
    <form method="post" action="{% url 'kit:demo-bulk' %}" hx-post="{% url 'kit:demo-bulk' %}" hx-swap="none" data-bulk>
      {% csrf_token %}
      <div class="bulk-bar" data-bulk-bar>
        <p class="bulk-bar__count" data-bulk-count aria-live="polite">Select applications, then choose an action.</p>
        <div class="btn-row">
          <button class="btn btn--primary" type="submit" name="action" value="approve">Approve selected</button>
          <button class="btn btn--secondary" type="submit" name="action" value="return">Return selected</button>
        </div>
      </div>
      <div class="table-wrap" role="region" aria-labelledby="bulk-caption" tabindex="0">
        <table class="table">
          <caption id="bulk-caption" class="visually-hidden">Applications</caption>
          <thead><tr><th scope="col" class="select"><input type="checkbox" data-bulk-all aria-label="Select all applications"></th><th scope="col">Applicant</th><th scope="col">School</th><th scope="col">Status</th></tr></thead>
          <tbody>
            {% for row in bulk_rows %}
            <tr>
              <td class="select"><input type="checkbox" name="ids" value="{{ row.id }}" data-bulk-item aria-label="Select {{ row.name }}"></td>
              <th scope="row">{{ row.name }}</th>
              <td>{{ row.school }}</td>
              <td><span class="pill pill--info">{% icon "file-text" %}Submitted</span></td>
            </tr>
            {% endfor %}
          </tbody>
        </table>
      </div>
    </form>
  </div>
</section>
```

- [ ] **Step 5: Kit views and URLs**

In `apps/kit/views.py`:
- add imports `from decimal import Decimal`, `from django.views.decorators.http import require_http_methods`, and
  `from apps.core.htmx import close_dialog` and `from apps.core.templatetags.ui import peso`;
- add `("overlays", "Dialogs and bulk actions")` to `SECTIONS`;
- add `"bulk_rows": samples.scholars()[:4],` to `index_context`'s return dict;
- add:
```python
RELEASE_AMOUNT = Decimal("60000.00")
RELEASE_COUNT = 12
BULK_VERBS = {"approve": "Approved", "return": "Returned"}


@kit_only
@require_http_methods(["GET", "POST"])
def demo_dialog(request: HtmxHttpRequest) -> HttpResponse:
    if request.method == "POST":
        text = f"Released {peso(RELEASE_AMOUNT)} to {RELEASE_COUNT} scholars"
        if request.htmx:
            return close_dialog(toast(HttpResponse(status=204), text))
        messages.success(request, text)
        return redirect(f"{reverse('kit:index')}#overlays")
    template = "kit/demo_dialog_fragment.html" if request.htmx else "kit/demo_dialog.html"
    return render(request, template, {"amount": RELEASE_AMOUNT, "count": RELEASE_COUNT})


@kit_only
@require_POST
def demo_bulk(request: HtmxHttpRequest) -> HttpResponse:
    known = {str(row["id"]) for row in samples.scholars()}
    ids = [value for value in request.POST.getlist("ids") if value in known]
    verb = BULK_VERBS.get(request.POST.get("action", ""))
    tone: Tone
    if not ids or verb is None:
        text, tone = "Select at least one application first.", "warning"
    else:
        text, tone = f"{verb} {len(ids)} application{'s' if len(ids) != 1 else ''}", "success"
    if request.htmx:
        return toast(HttpResponse(status=204), text, tone)
    messages.add_message(request, TONE_LEVELS[tone], text)
    return redirect(f"{reverse('kit:index')}#overlays")
```
`apps/kit/urls.py`, add:
```python
    path("demo/dialog/", views.demo_dialog, name="demo-dialog"),
    path("demo/bulk/", views.demo_bulk, name="demo-bulk"),
```

- [ ] **Step 6: Build and run all the tests**

```powershell
npm --prefix frontend run build
python -m uv run pytest -n auto
python -m uv run pytest -m e2e --ds=config.e2e_settings --browser chromium
python -m uv run mypy .; npm --prefix frontend run typecheck; npm --prefix frontend run check; npm --prefix frontend run budget
```
Expected: all PASS; clean.

- [ ] **Step 7: Commit**

```powershell
git add frontend/src/dialog.ts frontend/src/bulk.ts frontend/src/main.ts frontend/src/styles templates/base.html templates/components/dialog.html apps/kit tests/e2e/test_overlays.py
git commit -m "feat: add htmx dialogs and bulk-selection bar"
```

---

### Task 8: Layouts, collapsible navigation and error pages

**Files:**
- Create: `templates/layouts/public.html`, `auth.html`, `student.html`, `app.html`, `staff.html`, `office.html`
- Create: `templates/components/nav_list.html`
- Create: `templates/400.html`, `403.html`, `404.html`, `500.html`; modify `templates/core/home.html`
- Create: `frontend/src/nav.ts`, `frontend/src/styles/layouts.css`; modify `frontend/src/main.ts`
- Modify: `apps/kit/samples.py` (`chrome`), `apps/kit/views.py` (`layout_demo`, `demo_signout`),
  `apps/kit/urls.py`
- Create: `apps/kit/templates/kit/layout_demo.html`, `kit/sections/layouts.html`
- Modify: `CLAUDE.md` (file structure: `templates/layouts`, `components`)
- Test: `apps/core/tests/test_layouts.py`, `apps/core/tests/test_error_pages.py`; modify
  `apps/core/tests/test_security_headers.py` (add `vite_build` to the 404 test); create `tests/e2e/test_layouts.py`

**Interfaces:**
- Consumes: `.icon-btn`, `.btn`, `{% icon %}`, `breadcrumbs.html`.
- Produces:
  - **Layout context:** every key is optional unless marked.
    - `nav_items: list[NavItem]`, where `NavItem = {label, url, icon, current: bool, count: int}`;
    - `viewer: {name, role}` (student, staff and office). M4 replaces it with `request.user`;
    - `home_url`, `logout_url` (renders a POST sign-out form only when set), `notifications_url`,
      `notifications_count` (student);
    - `program: {name}` and `programs: list[{name, url, current}]` (staff, **required**);
    - `crumbs` (staff and office; rendered above the content).
  - **Blocks:** `title`, `content`; `breadcrumbs` in `app.html`; `sidebar_context` (used by staff and office).
  - **Classes:** `.topbar`, `.brand`, `.topnav`, `.shell`, `.sidebar`, `.sidenav`, `.switcher`, `.auth`,
    `.page-header`, `.split`, `.stack`, `.badge`, `.error-page`.
  - **TypeScript:** `nav.ts` exports `initNav()`.
  - **Python:** `samples.chrome(area: str, current: str = "") -> dict[str, object]`.
  - **URLs:** `kit:layout` (`/_kit/layouts/<name>/`), `kit:demo-signout` (POST).

- [ ] **Step 1: Write the failing tests**

`apps/core/tests/test_layouts.py`:
```python
import re

import pytest
from django.template.loader import render_to_string
from django.test import RequestFactory

NAV = [
    {"label": "Dashboard", "url": "/me/", "icon": "layout-dashboard", "current": True, "count": 0},
    {"label": "Applications", "url": "/me/applications/", "icon": "file-text", "current": False, "count": 2},
]
PROGRAMS = [
    {"name": "TCU CEAA", "url": "/staff/tcu-ceaa/", "current": True},
    {"name": "LANI", "url": "/staff/lani/", "current": False},
]


def render(template: str, **context) -> str:
    base = {
        "nav_items": NAV,
        "viewer": {"name": "Carolyn Hawkins", "role": "Student"},
        "program": {"name": "TCU CEAA"},
        "programs": PROGRAMS,
    }
    return render_to_string(template, {**base, **context}, request=RequestFactory().get("/"))


@pytest.mark.parametrize(
    "layout",
    ["layouts/public.html", "layouts/auth.html", "layouts/student.html", "layouts/staff.html", "layouts/office.html"],
)
def test_every_layout_has_one_main_a_skip_link_and_the_logo(layout, vite_build):
    html = render(layout)
    assert html.count('<main id="main"') == 1
    assert '<a class="skip-link" href="#main">' in html
    assert "icons.svg#logo" in html


def test_current_nav_item_is_marked(vite_build):
    html = render("layouts/student.html")
    assert '<a href="/me/" aria-current="page">' in html
    assert html.count('aria-current="page"') == 1
    assert '<span class="nav-count">2</span>' in html


def test_nav_toggle_is_hidden_until_javascript_runs(vite_build):
    html = render("layouts/staff.html")
    assert re.search(r"<button[^>]*data-nav-toggle[^>]*\bhidden>", html)


def test_program_switcher_lists_programs(vite_build):
    html = render("layouts/staff.html")
    assert '<a href="/staff/lani/">LANI</a>' in html
    assert '<a href="/staff/tcu-ceaa/" aria-current="true">TCU CEAA</a>' in html


def test_layouts_without_nav_have_no_menu_button(vite_build):
    assert "data-nav-toggle" not in render("layouts/public.html", nav_items=[])
    assert "data-nav-toggle" not in render("layouts/auth.html")


def test_sign_out_is_a_post_form_only_when_a_url_is_given(vite_build):
    html = render("layouts/office.html", logout_url="/accounts/logout/")
    assert '<form method="post" action="/accounts/logout/">' in html
    assert "csrfmiddlewaretoken" in html
    assert "Sign out" not in render("layouts/office.html")
```

`apps/core/tests/test_error_pages.py`:
```python
import pytest
from django.test import RequestFactory
from django.views import defaults


@pytest.mark.parametrize(
    ("view", "status", "heading"),
    [
        (lambda r: defaults.bad_request(r, Exception()), 400, "Something was wrong with that request"),
        (lambda r: defaults.permission_denied(r, Exception()), 403, "You can't open this page"),
        (lambda r: defaults.page_not_found(r, Exception()), 404, "Page not found"),
        (lambda r: defaults.server_error(r), 500, "Something went wrong on our side"),
    ],
)
def test_error_pages_use_the_public_layout(view, status, heading, vite_build):
    response = view(RequestFactory().get("/"))
    body = response.content.decode()
    assert response.status_code == status
    assert f"<h1>{heading}</h1>" in body
    assert '<main id="main"' in body


def test_unknown_url_renders_the_404_page(client, vite_build):
    response = client.get("/no-such-page/")
    assert response.status_code == 404
    assert "<h1>Page not found</h1>" in response.content.decode()
```

In `apps/core/tests/test_security_headers.py`, change `def test_security_headers_on_404(client):` to
`def test_security_headers_on_404(client, vite_build):` (the 404 page now renders the Vite assets).

`tests/e2e/test_layouts.py`:
```python
import pytest
from playwright.sync_api import Browser, Page, expect

pytestmark = pytest.mark.e2e

PHONE = {"width": 375, "height": 812}
DESKTOP = {"width": 1280, "height": 800}


@pytest.mark.parametrize("name", ["public", "auth", "student", "staff", "office"])
def test_layout_fits_a_phone_and_nav_toggles(page: Page, live_server, vite_build, console_errors, name):
    page.set_viewport_size(PHONE)
    page.goto(f"{live_server.url}/_kit/layouts/{name}/")
    assert page.evaluate("document.documentElement.scrollWidth") <= PHONE["width"]
    toggle = page.get_by_role("button", name="Menu")
    if name == "auth":
        expect(toggle).to_have_count(0)
    else:
        nav = page.get_by_role("navigation", name="Main")
        expect(nav).to_be_hidden()
        toggle.click()
        expect(toggle).to_have_attribute("aria-expanded", "true")
        expect(nav).to_be_visible()
    assert console_errors == []


def test_sidebar_is_open_on_desktop(page: Page, live_server, vite_build):
    page.set_viewport_size(DESKTOP)
    page.goto(f"{live_server.url}/_kit/layouts/staff/")
    expect(page.get_by_role("button", name="Menu")).to_be_hidden()
    expect(page.get_by_role("navigation", name="Main")).to_be_visible()


def test_nav_is_visible_without_javascript_on_a_phone(browser: Browser, live_server, vite_build):
    context = browser.new_context(java_script_enabled=False, viewport=PHONE)
    page = context.new_page()
    page.goto(f"{live_server.url}/_kit/layouts/staff/")
    expect(page.get_by_role("navigation", name="Main")).to_be_visible()
    expect(page.get_by_role("button", name="Menu")).to_be_hidden()
    context.close()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m uv run pytest apps/core/tests/test_layouts.py apps/core/tests/test_error_pages.py -q`
Expected: FAIL. `TemplateDoesNotExist: layouts/public.html`; the error pages show Django's defaults.

- [ ] **Step 3: Layout templates**

`templates/components/nav_list.html`:
```django
{% load ui %}<ul class="{{ list_class }}" role="list">
  {% for item in nav_items %}<li><a href="{{ item.url }}"{% if item.current %} aria-current="page"{% endif %}>{% if item.icon %}{% icon item.icon %}{% endif %}<span>{{ item.label }}</span>{% if item.count %}<span class="nav-count">{{ item.count }}</span>{% endif %}</a></li>{% endfor %}
</ul>
```

`templates/layouts/public.html`:
```django
{% extends "base.html" %}{% load ui %}
{% block body %}
<header class="topbar">
  <div class="container topbar__inner">
    <a class="brand" href="{% url 'core:home' %}">{% icon "logo" %}<span>ScholarSync</span></a>
    {% if nav_items %}
    <button type="button" class="icon-btn nav-toggle" data-nav-toggle aria-controls="site-nav" aria-expanded="false" aria-label="Menu" hidden>{% icon "menu" %}</button>
    <nav id="site-nav" class="topnav" aria-label="Main">{% include "components/nav_list.html" with list_class="topnav__list" %}</nav>
    {% endif %}
  </div>
</header>
<main id="main" tabindex="-1" class="container page">
  {% block content %}{% endblock %}
</main>
<footer class="footer">
  <div class="container"><p>ScholarSync is the scholarship platform of the City of Taguig.</p></div>
</footer>
{% endblock %}
```

`templates/layouts/auth.html`:
```django
{% extends "base.html" %}{% load ui %}
{% block body %}
<div class="auth">
  <div class="auth__panel">
    <a class="brand" href="{% url 'core:home' %}">{% icon "logo" %}<span>ScholarSync</span></a>
    <div>
      <p class="auth__tagline">Scholarships for the students of Taguig.</p>
      <p class="auth__note">Apply to city scholarship programs, upload your documents once, and follow your allowances term by term.</p>
    </div>
  </div>
  <main id="main" tabindex="-1" class="auth__main">
    <div class="auth__form">{% block content %}{% endblock %}</div>
  </main>
</div>
{% endblock %}
```

`templates/layouts/student.html`:
```django
{% extends "base.html" %}{% load ui %}
{% block body %}
<header class="topbar">
  <div class="container topbar__inner">
    <a class="brand" href="{{ home_url|default:'/' }}">{% icon "logo" %}<span>ScholarSync</span></a>
    <button type="button" class="icon-btn nav-toggle" data-nav-toggle aria-controls="student-nav" aria-expanded="false" aria-label="Menu" hidden>{% icon "menu" %}</button>
    <div id="student-nav" class="topnav">
      <nav aria-label="Main">{% include "components/nav_list.html" with list_class="topnav__list" %}</nav>
      <div class="topnav__account">
        {% if notifications_url %}<a class="icon-btn" href="{{ notifications_url }}" aria-label="Notifications{% if notifications_count %}, {{ notifications_count }} unread{% endif %}">{% icon "bell" %}{% if notifications_count %}<span class="badge" aria-hidden="true">{{ notifications_count }}</span>{% endif %}</a>{% endif %}
        {% if viewer %}<span class="topnav__viewer">{{ viewer.name }}</span>{% endif %}
        {% if logout_url %}<form method="post" action="{{ logout_url }}">{% csrf_token %}<button type="submit" class="btn btn--ghost">{% icon "log-out" %}Sign out</button></form>{% endif %}
      </div>
    </div>
  </div>
</header>
<main id="main" tabindex="-1" class="container page">
  {% block content %}{% endblock %}
</main>
{% endblock %}
```

`templates/layouts/app.html` (the sidebar shell for staff and office):
```django
{% extends "base.html" %}{% load ui %}
{% block body %}
<div class="shell">
  <div class="sidebar">
    <div class="sidebar__top">
      <a class="brand" href="{{ home_url|default:'/' }}">{% icon "logo" %}<span>ScholarSync</span></a>
      <button type="button" class="icon-btn nav-toggle" data-nav-toggle aria-controls="app-nav" aria-expanded="false" aria-label="Menu" hidden>{% icon "menu" %}</button>
    </div>
    <div id="app-nav" class="sidebar__nav">
      {% block sidebar_context %}{% endblock %}
      <nav class="sidenav" aria-label="Main">{% include "components/nav_list.html" with list_class="sidenav__list" %}</nav>
      <div class="sidebar__footer">
        {% if viewer %}<p class="sidebar__viewer">{{ viewer.name }}<span>{{ viewer.role }}</span></p>{% endif %}
        {% if logout_url %}<form method="post" action="{{ logout_url }}">{% csrf_token %}<button type="submit" class="sidebar__signout">{% icon "log-out" %}Sign out</button></form>{% endif %}
      </div>
    </div>
  </div>
  <main id="main" tabindex="-1" class="shell__main page">
    {% block breadcrumbs %}{% if crumbs %}{% include "components/breadcrumbs.html" %}{% endif %}{% endblock %}
    {% block content %}{% endblock %}
  </main>
</div>
{% endblock %}
```

`templates/layouts/staff.html`:
```django
{% extends "layouts/app.html" %}{% load ui %}
{% block sidebar_context %}
<details class="switcher">
  <summary><span><span class="switcher__label">Program</span>{{ program.name }}</span>{% icon "chevrons-up-down" %}</summary>
  <ul role="list">{% for item in programs %}<li><a href="{{ item.url }}"{% if item.current %} aria-current="true"{% endif %}>{{ item.name }}</a></li>{% endfor %}</ul>
</details>
{% endblock %}
```

`templates/layouts/office.html`:
```django
{% extends "layouts/app.html" %}
{% block sidebar_context %}<p class="sidebar__area">Scholarship office</p>{% endblock %}
```

`templates/core/home.html`:
```django
{% extends "layouts/public.html" %}
{% block title %}Scholarships{% endblock %}
{% block content %}
  <h1>ScholarSync</h1>
  <p>The City of Taguig scholarship platform is being rebuilt. Programs and applications open here soon.</p>
{% endblock %}
```

`templates/404.html`:
```django
{% extends "layouts/public.html" %}
{% block title %}Page not found{% endblock %}
{% block content %}
<div class="error-page">
  <h1>Page not found</h1>
  <p>Check the address, or go back to the home page.</p>
  <a class="btn btn--primary" href="{% url 'core:home' %}">Go to the home page</a>
</div>
{% endblock %}
```

`templates/403.html`: the same structure with title and `h1` "You can't open this page" and the text: "Your account
doesn't have access to this page. If you think it should, contact the scholarship office."

`templates/400.html`: title and `h1` "Something was wrong with that request", text: "Go back and try again."

`templates/500.html`: title and `h1` "Something went wrong on our side", text: "Try again in a few minutes. If it
keeps happening, contact the scholarship office." (Django renders 500.html without a request; the public layout
uses only `{% url %}`, `{% static %}` and the Vite tags, all of which work without one.)

- [ ] **Step 4: `nav.ts` and layout CSS**

`frontend/src/nav.ts`:
```ts
// Collapsible navigation below 64rem (spec §12). Without JS the navigation stays open and the toggle
// stays hidden (it carries the hidden attribute until this runs).

export function initNav(): void {
  for (const toggle of document.querySelectorAll<HTMLButtonElement>("[data-nav-toggle]")) {
    const nav = document.getElementById(toggle.getAttribute("aria-controls") ?? "");
    if (!nav) continue;
    nav.classList.add("is-collapsible");
    toggle.hidden = false;
    toggle.addEventListener("click", () => {
      const open = toggle.getAttribute("aria-expanded") !== "true";
      toggle.setAttribute("aria-expanded", String(open));
      nav.classList.toggle("is-open", open);
    });
  }
}
```

`frontend/src/styles/layouts.css`:
```css
/* Shared */
.brand {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  min-height: var(--control-height);
  color: var(--brand-600);
  font-family: var(--font-heading);
  font-size: var(--text-xl);
  font-weight: 700;
  text-decoration: none;
}

.brand:hover {
  color: var(--brand-700);
}

.brand .icon {
  width: 1.75rem;
  height: 1.75rem;
}

.nav-count,
.badge {
  display: inline-grid;
  place-items: center;
  min-width: 1.25rem;
  height: 1.25rem;
  padding: 0 0.3rem;
  border-radius: var(--radius-full);
  background: var(--brand-600);
  color: var(--text-inverse);
  font-size: 0.75rem;
  font-weight: 600;
  line-height: 1;
}

.nav-count {
  margin-left: auto;
}

.badge {
  position: absolute;
  top: 0.2rem;
  right: 0.2rem;
}

.page-header {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  justify-content: space-between;
  gap: var(--space-4);
  margin-bottom: var(--space-6);
}

.page-header h1 {
  margin: 0;
}

.page-header__meta {
  margin: var(--space-1) 0 0;
  color: var(--text-muted);
}

.split {
  display: grid;
  gap: var(--space-6);
}

@media (min-width: 64rem) {
  .split {
    grid-template-columns: minmax(0, 2fr) minmax(18rem, 1fr);
    align-items: start;
  }
}

.stack {
  display: grid;
  gap: var(--space-6);
  min-width: 0;
}

.error-page {
  padding-block: var(--space-12);
}

.footer {
  padding-block: var(--space-8);
  border-top: 1px solid var(--border);
  color: var(--text-muted);
  font-size: var(--text-sm);
}

/* Collapsible navigation (nav.ts) */
@media (min-width: 64rem) {
  .nav-toggle {
    display: none;
  }
}

@media (max-width: 63.99rem) {
  .is-collapsible:not(.is-open) {
    display: none;
  }
}

/* Top bar: public and student */
.topbar {
  border-bottom: 1px solid var(--border);
  background: var(--surface);
  box-shadow: inset 0 -3px 0 var(--accent);
}

.topbar__inner {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2) var(--space-6);
  min-height: 4rem;
  padding-block: var(--space-2);
}

.nav-toggle {
  margin-left: auto;
}

.topnav {
  display: flex;
  flex: 1;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2) var(--space-4);
}

.topnav__list {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-1);
  margin: 0;
  padding: 0;
  list-style: none;
}

.topnav__list a {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  min-height: var(--control-height);
  padding: 0 var(--space-3);
  border-radius: var(--radius-md);
  color: var(--text-muted);
  font-weight: 500;
  text-decoration: none;
}

.topnav__list a:hover {
  background: var(--surface-sunken);
  color: var(--text);
}

.topnav__list a[aria-current="page"] {
  background: var(--brand-50);
  color: var(--brand-600);
}

.topnav__account {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2);
}

.topnav__account form {
  margin: 0;
}

.topnav__viewer {
  font-weight: 500;
}

@media (max-width: 63.99rem) {
  .topnav {
    flex-basis: 100%;
    flex-direction: column;
    align-items: stretch;
    padding-bottom: var(--space-3);
  }

  .topnav__list {
    flex-direction: column;
  }

  .topnav__account {
    padding-top: var(--space-3);
    border-top: 1px solid var(--border);
  }
}

/* Sidebar shell: staff and office */
.shell {
  display: grid;
  min-height: 100vh;
}

@media (min-width: 64rem) {
  .shell {
    grid-template-columns: var(--sidebar-width) minmax(0, 1fr);
  }
}

.sidebar {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  padding: var(--space-3) var(--space-4);
  background: var(--nav-bg);
  color: var(--nav-text);
}

@media (min-width: 64rem) {
  .sidebar {
    position: sticky;
    top: 0;
    height: 100vh;
    padding-block: var(--space-5);
    overflow-y: auto;
  }
}

.sidebar :focus-visible {
  outline-color: var(--nav-marker);
}

.sidebar .brand,
.sidebar .brand:hover {
  color: var(--nav-text);
}

.sidebar .icon-btn {
  color: var(--nav-text);
}

.sidebar .icon-btn:hover {
  background: var(--nav-bg-hover);
}

.sidebar__top {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.sidebar__nav {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: var(--space-4);
}

.sidebar__area {
  margin: 0;
  color: var(--nav-text-muted);
  font-size: var(--text-sm);
}

.sidenav__list {
  display: grid;
  gap: 2px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.sidenav__list a {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  min-height: var(--control-height);
  padding: 0 var(--space-3);
  border-radius: var(--radius-md);
  color: var(--nav-text-muted);
  font-weight: 500;
  text-decoration: none;
}

.sidenav__list a:hover {
  background: var(--nav-bg-hover);
  color: var(--nav-text);
}

.sidenav__list a[aria-current="page"] {
  background: var(--nav-bg-hover);
  box-shadow: inset 3px 0 0 var(--nav-marker);
  color: var(--nav-text);
}

.sidebar__footer {
  margin-top: auto;
  padding-top: var(--space-4);
  border-top: 1px solid var(--nav-bg-hover);
}

.sidebar__viewer {
  display: grid;
  margin: 0 0 var(--space-2);
  font-weight: 600;
}

.sidebar__viewer span {
  color: var(--nav-text-muted);
  font-size: var(--text-sm);
  font-weight: 400;
}

.sidebar__signout {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  min-height: var(--control-height);
  padding: 0;
  border: 0;
  background: none;
  color: var(--nav-text-muted);
  font: inherit;
  cursor: pointer;
}

.sidebar__signout:hover {
  color: var(--nav-text);
}

.switcher {
  position: relative;
}

.switcher summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  min-height: var(--control-height);
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--nav-text-muted);
  border-radius: var(--radius-md);
  font-weight: 600;
  list-style: none;
  cursor: pointer;
}

.switcher summary::-webkit-details-marker {
  display: none;
}

.switcher__label {
  display: block;
  color: var(--nav-text-muted);
  font-size: var(--text-sm);
  font-weight: 400;
}

.switcher ul {
  position: absolute;
  z-index: 10;
  top: calc(100% + var(--space-1));
  inset-inline: 0;
  margin: 0;
  padding: var(--space-1);
  border-radius: var(--radius-md);
  background: var(--surface);
  box-shadow: var(--shadow-2);
  list-style: none;
}

.switcher ul a {
  display: flex;
  align-items: center;
  min-height: var(--control-height);
  padding: 0 var(--space-3);
  border-radius: var(--radius-sm);
  color: var(--text);
  text-decoration: none;
}

.switcher ul a:hover {
  background: var(--surface-sunken);
}

.switcher ul a[aria-current="true"] {
  color: var(--brand-600);
  font-weight: 600;
}

.sidebar .switcher ul :focus-visible {
  outline-color: var(--focus);
}

.shell__main {
  min-width: 0;
  width: 100%;
  max-width: var(--content-max);
  padding-inline: var(--space-4);
}

@media (min-width: 64rem) {
  .shell__main {
    padding-inline: var(--space-8);
  }
}

/* Auth: split panel, as in v1 */
.auth {
  display: grid;
  min-height: 100vh;
  background: var(--surface);
}

@media (min-width: 56rem) {
  .auth {
    grid-template-columns: minmax(0, 5fr) minmax(0, 6fr);
  }
}

.auth__panel {
  display: flex;
  flex-direction: column;
  gap: var(--space-6);
  padding: var(--space-6);
  border-bottom: 4px solid var(--accent);
  background: var(--nav-bg);
  color: var(--nav-text);
}

@media (min-width: 56rem) {
  .auth__panel {
    justify-content: space-between;
    padding: var(--space-12);
    border-right: 4px solid var(--accent);
    border-bottom: 0;
  }
}

.auth__panel .brand,
.auth__panel .brand:hover {
  color: var(--nav-text);
}

.auth__panel :focus-visible {
  outline-color: var(--nav-marker);
}

.auth__tagline {
  max-width: 16ch;
  margin: 0 0 var(--space-4);
  color: var(--nav-text);
  font-family: var(--font-heading);
  font-size: var(--text-3xl);
  font-weight: 700;
  line-height: var(--leading-tight);
}

.auth__note {
  max-width: 40ch;
  margin: 0;
  color: var(--nav-text-muted);
}

.auth__main {
  display: flex;
  align-items: center;
}

.auth__form {
  width: 100%;
  max-width: 28rem;
  margin-inline: auto;
  padding: var(--space-8) var(--space-6);
}
```

`frontend/src/main.ts`: add `import "./styles/layouts.css";` after the `data.css` import, add `import { initNav }
from "./nav";` between the `./dialog` and `./toast` imports, and call `initNav();` after `initBulk();`.

- [ ] **Step 5: Kit layout demos and the sign-out stub**

Add to `apps/kit/samples.py`:
```python
from django.urls import reverse


class NavItem(TypedDict):
    label: str
    url: str
    icon: str
    current: bool
    count: int


PUBLIC_NAV = [("Programs", "school", 0), ("Help", "info", 0)]
STUDENT_NAV = [
    ("Dashboard", "layout-dashboard", 0),
    ("Profile", "user", 0),
    ("Find programs", "search", 0),
    ("Applications", "file-text", 1),
    ("Scholarships", "wallet", 0),
]
STAFF_NAV = [
    ("Dashboard", "layout-dashboard", 0),
    ("Applications", "file-text", 14),
    ("Scholars", "users", 0),
    ("Terms", "calendar", 0),
    ("Disbursements", "banknote", 0),
    ("Budget", "wallet", 0),
    ("Reports", "chart-column", 0),
    ("Tasks", "list-checks", 3),
    ("Settings", "settings", 0),
]
OFFICE_NAV = [
    ("Overview", "layout-dashboard", 0),
    ("Programs", "school", 0),
    ("Staff", "shield-check", 0),
    ("Scholars", "users", 0),
    ("Reports", "file-check", 3),
    ("Analytics", "chart-column", 0),
    ("Audit log", "eye", 0),
    ("Schools", "building-2", 0),
    ("Terms", "calendar", 0),
]


def nav(items: list[tuple[str, str, int]], current: str) -> list[NavItem]:
    return [
        {"label": label, "url": "#", "icon": icon, "current": label == current, "count": count}
        for label, icon, count in items
    ]


def chrome(area: str, current: str = "") -> dict[str, object]:
    """Layout context for a sample page in one area (public, auth, student, staff, office)."""
    signed_in = {"home_url": "#", "logout_url": reverse("kit:demo-signout")}
    if area == "public":
        return {"nav_items": nav(PUBLIC_NAV, current)}
    if area == "auth":
        return {}
    if area == "student":
        return {
            **signed_in,
            "nav_items": nav(STUDENT_NAV, current or "Dashboard"),
            "viewer": {"name": "Carolyn Hawkins", "first_name": "Carolyn", "role": "Student"},
            "notifications_url": "#",
            "notifications_count": 2,
        }
    if area == "staff":
        return {
            **signed_in,
            "nav_items": nav(STAFF_NAV, current or "Dashboard"),
            "viewer": {"name": "Krista Kelley", "role": "Program staff"},
            "program": {"name": "TCU CEAA"},
            "programs": [
                {"name": "TCU CEAA", "url": "#", "current": True},
                {"name": "LANI", "url": "#", "current": False},
            ],
        }
    if area == "office":
        return {
            **signed_in,
            "nav_items": nav(OFFICE_NAV, current or "Overview"),
            "viewer": {"name": "Jessica Tate", "role": "Scholarship office"},
        }
    raise ValueError(f"unknown area {area!r}")
```

In `apps/kit/views.py`:
- add `("layouts", "Layouts")` to `SECTIONS`;
- add `"layout_names": list(LAYOUTS)` to `index_context`;
- add:
```python
LAYOUTS = {
    "public": "layouts/public.html",
    "auth": "layouts/auth.html",
    "student": "layouts/student.html",
    "staff": "layouts/staff.html",
    "office": "layouts/office.html",
}


@kit_only
@require_safe
def layout_demo(request: HttpRequest, name: str) -> HttpResponse:
    if name not in LAYOUTS:
        raise Http404
    context = {"layout": LAYOUTS[name], "name": name, **samples.chrome(name)}
    if name in {"staff", "office"}:
        context["crumbs"] = [{"label": "Design kit", "url": reverse("kit:index")}, {"label": "Layouts", "url": ""}]
    return render(request, "kit/layout_demo.html", context)


@kit_only
@require_POST
def demo_signout(request: HttpRequest) -> HttpResponse:
    messages.info(request, "Sign-out arrives with accounts in M4.")
    return redirect(f"{reverse('kit:index')}#layouts")
```

`apps/kit/urls.py`, add:
```python
    path("layouts/<slug:name>/", views.layout_demo, name="layout"),
    path("demo/signout/", views.demo_signout, name="demo-signout"),
```

`apps/kit/templates/kit/layout_demo.html`:
```django
{% extends layout %}
{% block title %}{{ name|capfirst }} layout{% endblock %}
{% block content %}
<div class="page-header"><div><h1>{{ name|capfirst }} layout</h1><p class="page-header__meta">Sample navigation and content.</p></div></div>
<div class="card"><p>Page content goes here. Below 64rem wide, the navigation collapses behind the menu button.</p><p><a href="{% url 'kit:index' %}#layouts">Back to the design kit</a></p></div>
{% endblock %}
```

`apps/kit/templates/kit/sections/layouts.html`:
```django
<section class="kit-section" id="layouts" aria-labelledby="layouts-title">
  <h2 id="layouts-title">Layouts</h2>
  <p>Each layout with sample navigation. Staff and office share the sidebar shell; staff adds the program switcher.</p>
  <ul>{% for name in layout_names %}<li><a href="{% url 'kit:layout' name %}">{{ name|capfirst }} layout</a></li>{% endfor %}</ul>
</section>
```

`CLAUDE.md`: in the file structure, change the `templates/` line to `base.html, layouts/ (public, auth, student,
app → staff/office), components/, 4xx/500 pages`.

- [ ] **Step 6: Build and run all the tests**

```powershell
npm --prefix frontend run build
python -m uv run pytest -n auto
python -m uv run pytest -m e2e --ds=config.e2e_settings --browser chromium
python -m uv run mypy .; npm --prefix frontend run typecheck; npm --prefix frontend run check; npm --prefix frontend run budget
```
Expected: all PASS; clean.

- [ ] **Step 7: Commit**

```powershell
git add templates frontend/src/nav.ts frontend/src/main.ts frontend/src/styles/layouts.css apps/core/tests/test_layouts.py apps/core/tests/test_error_pages.py apps/core/tests/test_security_headers.py apps/kit tests/e2e/test_layouts.py CLAUDE.md
git commit -m "feat: add public, auth, student, staff and office layouts"
```

---

### Task 9: Key-screen mockups

**Files:**
- Modify: `apps/kit/samples.py` (one context builder per mockup), `apps/kit/forms.py` (`ApplyForm`,
  `DecisionForm`), `apps/kit/views.py`, `apps/kit/urls.py`
- Create: `apps/kit/templates/kit/mockups/index.html`, `student_dashboard.html`, `apply.html`,
  `application_review.html`, `disbursements.html`, `office_dashboard.html`
- Modify: `kit/index.html` (a link to the mockups)
- Test: `apps/kit/tests/test_mockups.py`, `tests/e2e/test_mockups.py`

**Interfaces:**
- Consumes: every component, layout and tag from Tasks 1–8, and `samples.chrome`.
- Produces:
  - `apps.kit.views.MOCKUPS: dict[str, tuple[str, str, Callable[[], dict[str, object]]]]` (slug → title, template,
    builder);
  - URL names `kit:mockups` (`/_kit/mockups/`) and `kit:mockup` (`/_kit/mockups/<slug>/`).

- [ ] **Step 1: Write the failing tests**

`apps/kit/tests/test_mockups.py`:
```python
import re

import pytest

from apps.kit.views import LAYOUTS, MOCKUPS, icon_names


@pytest.fixture
def kit_on(settings):
    settings.KIT_ENABLED = True


@pytest.mark.parametrize("slug", list(MOCKUPS))
def test_mockup_renders_with_one_h1(client, kit_on, vite_build, slug):
    response = client.get(f"/_kit/mockups/{slug}/")
    body = response.content.decode()
    assert response.status_code == 200
    assert response["X-Robots-Tag"] == "noindex, nofollow"
    assert body.count("<h1") == 1
    assert body.count('<main id="main"') == 1


def test_unknown_mockup_is_404(client, kit_on):
    assert client.get("/_kit/mockups/nope/").status_code == 404


def test_mockup_index_links_every_mockup(client, kit_on, vite_build):
    body = client.get("/_kit/mockups/").content.decode()
    for slug in MOCKUPS:
        assert f'href="/_kit/mockups/{slug}/"' in body


def test_kit_pages_only_use_icons_in_the_sprite(client, kit_on, vite_build):
    urls = ["/_kit/", "/_kit/mockups/"]
    urls += [f"/_kit/layouts/{name}/" for name in LAYOUTS]
    urls += [f"/_kit/mockups/{slug}/" for slug in MOCKUPS]
    known = set(icon_names())
    for url in urls:
        used = set(re.findall(r'icons\.svg#([a-z0-9-]+)"', client.get(url).content.decode()))
        assert used <= known, (url, used - known)
```

`tests/e2e/test_mockups.py`:
```python
import os
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

from apps.kit.views import MOCKUPS

pytestmark = pytest.mark.e2e

VIEWPORTS = {"phone": {"width": 375, "height": 812}, "desktop": {"width": 1440, "height": 900}}


@pytest.mark.parametrize("viewport", list(VIEWPORTS))
@pytest.mark.parametrize("slug", list(MOCKUPS))
def test_mockup_fits_and_has_no_errors(page: Page, live_server, vite_build, console_errors, slug, viewport):
    size = VIEWPORTS[viewport]
    page.set_viewport_size(size)
    page.goto(f"{live_server.url}/_kit/mockups/{slug}/")
    expect(page.get_by_role("heading", level=1)).to_be_visible()
    assert page.evaluate("document.documentElement.scrollWidth") <= size["width"]
    assert console_errors == []
    if folder := os.environ.get("MOCKUP_SCREENSHOTS"):
        page.screenshot(path=Path(folder) / f"{slug}-{viewport}.png", full_page=True)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m uv run pytest apps/kit/tests/test_mockups.py -q`
Expected: FAIL with `ImportError: cannot import name 'MOCKUPS'`.

- [ ] **Step 3: Forms and sample contexts**

Add to `apps/kit/forms.py`:
```python
class ApplyForm(forms.Form):
    declaration = forms.BooleanField(
        label="The information and documents I submit are true and complete.",
        help_text="False statements end your scholarship and may be reported to the city.",
    )


class DecisionForm(forms.Form):
    tier = forms.ChoiceField(
        label="Benefit tier",
        choices=[("basic", "Basic, ₱5,000.00 a term"), ("priority", "Priority, ₱7,500.00 a term"),
                 ("honors", "Honors, ₱10,000.00 a term")],
        initial="priority",
    )
    note = forms.CharField(
        label="Message to the applicant",
        widget=forms.Textarea,
        required=False,
        help_text="Required when you return or reject an application. The applicant sees it.",
    )
```

Add to `apps/kit/samples.py` (add `from django.core.paginator import Paginator` and `from apps.kit.forms import
ApplyForm, DecisionForm` to the imports):
```python
def student_dashboard() -> dict[str, object]:
    return {
        **chrome("student", "Dashboard"),
        "award": {"program": "TCU CEAA", "tier": "Priority", "amount": Decimal("7500.00")},
        "applications": [
            {"program": "TCU CEAA", "submitted": "12 Jun 2026", "label": "Approved", "tone": "success", "icon": "circle-check"},
            {"program": "LANI", "submitted": "2 Oct 2026", "label": "Returned", "tone": "warning", "icon": "triangle-alert"},
        ],
        "allowances": [
            {"term": "1st semester, 2026–2027", "amount": Decimal("7500.00"), "label": "Scheduled 14 Nov", "tone": "info", "icon": "calendar"},
            {"term": "2nd semester, 2025–2026", "amount": Decimal("7500.00"), "label": "Released", "tone": "success", "icon": "circle-check"},
            {"term": "1st semester, 2025–2026", "amount": Decimal("5000.00"), "label": "Released", "tone": "success", "icon": "circle-check"},
        ],
        "notices": [
            {"text": "LANI returned your application: upload a clearer certificate of grades.", "when": "20 Oct"},
            {"text": "Your 1st semester allowance is scheduled for 14 November.", "when": "15 Oct"},
        ],
    }


def apply() -> dict[str, object]:
    return {
        **chrome("student", "Find programs"),
        "crumbs": [{"label": "Find programs", "url": "#"}, {"label": "LANI", "url": ""}],
        "documents": [
            {"id": "doc-grades", "label": "Certificate of grades", "help": "Your latest report card or certificate of grades.", "state": "done", "filename": "grades-2026.pdf"},
            {"id": "doc-residency", "label": "Proof of Taguig residency", "help": "Voter's certificate or barangay certificate.", "state": "uploading", "progress": 60, "filename": "barangay-certificate.jpg"},
            {"id": "doc-enrollment", "label": "Certificate of enrollment", "help": "For the 1st semester, 2026–2027.", "state": "error", "error": "This file is 14 MB. Upload a file of 10 MB or less."},
            {"id": "doc-id", "label": "Valid ID", "help": "School ID or any government ID.", "state": "idle"},
        ],
        "rules": [
            {"text": "Taguig resident for at least 3 years", "state": "met", "icon": "circle-check", "status": "Met"},
            {"text": "Enrolled in a recognized school", "state": "met", "icon": "circle-check", "status": "Met"},
            {"text": "Family income up to ₱400,000.00 a year", "state": "met", "icon": "circle-check", "status": "Met"},
            {"text": "GWA of 85% or better", "state": "pending", "icon": "info", "status": "Checked after you upload your grades"},
        ],
        "form": ApplyForm(),
    }


def application_review() -> dict[str, object]:
    return {
        **chrome("staff", "Applications"),
        "crumbs": [{"label": "Applications", "url": "#"}, {"label": "APP-2026-0147", "url": ""}],
        "tabs": [
            {"label": "Overview", "url": "#", "current": True, "count": 0},
            {"label": "Documents", "url": "#", "current": False, "count": 4},
            {"label": "Profile", "url": "#", "current": False, "count": 0},
            {"label": "History", "url": "#", "current": False, "count": 0},
        ],
        "applicant": {"name": "Daniel Montoya", "school": "Taguig City University", "course": "BS Information Technology, 2nd year", "gwa": "1.75 (88%)", "income": Decimal("312000.00"), "barangay": "Western Bicutan"},
        "documents": [
            {"label": "Certificate of grades", "file": "grades-2026.pdf", "status": "Approved", "tone": "success", "icon": "circle-check"},
            {"label": "Proof of residency", "file": "voters-certificate.pdf", "status": "Approved", "tone": "success", "icon": "circle-check"},
            {"label": "Certificate of enrollment", "file": "enrollment.jpg", "status": "Waiting", "tone": "info", "icon": "file-text"},
            {"label": "Valid ID", "file": "school-id.jpg", "status": "Declined", "tone": "danger", "icon": "circle-alert"},
        ],
        "rules": [
            {"text": "Taguig resident for at least 3 years", "state": "met", "icon": "circle-check", "status": "Met"},
            {"text": "Family income up to ₱400,000.00 a year", "state": "met", "icon": "circle-check", "status": "Met (₱312,000.00)"},
            {"text": "GWA of 85% or better", "state": "met", "icon": "circle-check", "status": "Met (88%)"},
            {"text": "No other city scholarship this term", "state": "unmet", "icon": "circle-alert", "status": "Not met: holds TCU CEAA"},
        ],
        "history": [
            {"what": "Valid ID declined", "when": "21 Oct 2026, 10:32 AM", "datetime": "2026-10-21T10:32+08:00", "who": "Krista Kelley"},
            {"what": "Review started", "when": "21 Oct 2026, 10:05 AM", "datetime": "2026-10-21T10:05+08:00", "who": "Krista Kelley"},
            {"what": "Submitted", "when": "2 Oct 2026, 9:14 AM", "datetime": "2026-10-02T09:14+08:00", "who": "the applicant"},
        ],
        "decision_form": DecisionForm(),
    }


def disbursements() -> dict[str, object]:
    statuses = [("Prepared", "neutral", "file-text"), ("Approved", "info", "circle-check"), ("Released", "success", "banknote")]
    rows = [
        {"id": row["id"], "name": row["name"], "tier": row["tier"], "amount": row["amount"],
         "label": statuses[index % 3][0], "tone": statuses[index % 3][1], "icon": statuses[index % 3][2]}
        for index, row in enumerate(scholars())
    ]
    return {
        **chrome("staff", "Disbursements"),
        "tabs": [
            {"label": "Disbursements", "url": "#", "current": True, "count": 0},
            {"label": "Schedules", "url": "#", "current": False, "count": 0},
            {"label": "Budget", "url": "#", "current": False, "count": 0},
        ],
        "budget": {"total": Decimal("12000000.00"), "released": Decimal("6480000.00"), "committed": Decimal("1250000.00"), "available": Decimal("4270000.00"), "used_percent": 64},
        "page": Paginator(rows, 8).get_page(1),
        "total": len(rows),
    }


def office_dashboard() -> dict[str, object]:
    return {
        **chrome("office", "Overview"),
        "programs": [
            {"name": "TCU CEAA", "window": "Closed", "applications": 412, "scholars": 968, "used_percent": 64},
            {"name": "LANI", "window": "Open until 15 Nov", "applications": 233, "scholars": 316, "used_percent": 41},
        ],
        "months": [
            {"label": "June", "count": 182}, {"label": "July", "count": 96}, {"label": "August", "count": 54},
            {"label": "September", "count": 71}, {"label": "October", "count": 242},
        ],
        "attention": [
            {"text": "3 program reports are waiting for your review", "icon": "file-check"},
            {"text": "LANI: 12 applications have waited more than 7 days", "icon": "triangle-alert"},
            {"text": "TCU CEAA has used 64% of its budget with 2 months left", "icon": "wallet"},
        ],
        "activity": [
            {"what": "Krista Kelley approved 14 disbursements (TCU CEAA)", "when": "Today, 9:40 AM", "datetime": "2026-10-28T09:40+08:00"},
            {"what": "Shannon Briggs opened LANI applications", "when": "Yesterday, 4:12 PM", "datetime": "2026-10-27T16:12+08:00"},
            {"what": "Jessica Tate added Technological University of the Philippines", "when": "25 Oct, 11:03 AM", "datetime": "2026-10-25T11:03+08:00"},
        ],
        "max_month": 242,
    }
```

Then run `python -m uv run ruff format apps/kit`; it wraps these literals one key per line. If `ruff check` still
reports E501 for a long string, split it with implicit concatenation (`"first half " "second half"`).

- [ ] **Step 4: Views and URLs**

In `apps/kit/views.py`, add:
```python
MOCKUPS: dict[str, tuple[str, str, Callable[[], dict[str, object]]]] = {
    "student-dashboard": ("Student dashboard", "kit/mockups/student_dashboard.html", samples.student_dashboard),
    "apply": ("Apply to a program", "kit/mockups/apply.html", samples.apply),
    "application-review": ("Staff application review", "kit/mockups/application_review.html", samples.application_review),
    "disbursements": ("Disbursements", "kit/mockups/disbursements.html", samples.disbursements),
    "office-dashboard": ("Office dashboard", "kit/mockups/office_dashboard.html", samples.office_dashboard),
}


@kit_only
@require_safe
def mockups(request: HttpRequest) -> HttpResponse:
    items = [{"slug": slug, "title": title} for slug, (title, _, _) in MOCKUPS.items()]
    return render(request, "kit/mockups/index.html", {"mockups": items})


@kit_only
@require_safe
def mockup(request: HttpRequest, slug: str) -> HttpResponse:
    if slug not in MOCKUPS:
        raise Http404
    _, template, build = MOCKUPS[slug]
    return render(request, template, build())
```

`apps/kit/urls.py`, add:
```python
    path("mockups/", views.mockups, name="mockups"),
    path("mockups/<slug:slug>/", views.mockup, name="mockup"),
```

In `kit/index.html`, add after the intro paragraph:
`<p><a class="btn btn--secondary" href="{% url 'kit:mockups' %}">Key-screen mockups</a></p>`

- [ ] **Step 5: Mockup templates**

`apps/kit/templates/kit/mockups/index.html`:
```django
{% extends "kit/base.html" %}
{% block title %}Key-screen mockups{% endblock %}
{% block content %}
<h1>Key-screen mockups</h1>
<p>Five screens built from the real components and layouts with sample data, for approval before M4 (spec §16, M3 gate). Buttons don't act; links go nowhere.</p>
<ul class="list">
  {% for item in mockups %}<li><a href="{% url 'kit:mockup' item.slug %}">{{ item.title }}</a></li>{% endfor %}
</ul>
{% endblock %}
```

`apps/kit/templates/kit/mockups/student_dashboard.html`:
```django
{% extends "layouts/student.html" %}{% load ui %}
{% block title %}Dashboard{% endblock %}
{% block content %}
<div class="page-header">
  <div><h1>Hello, {{ viewer.first_name }}</h1><p class="page-header__meta">1st semester, school year 2026–2027</p></div>
</div>
<div class="alert alert--warning" role="status">{% icon "triangle-alert" %}<div><p class="alert__title">LANI returned your application</p><p>Your certificate of grades is hard to read. Upload a clearer copy by 7 November 2026.</p><p><a href="#">Fix your application</a></p></div></div>
<div class="split">
  <div class="stack">
    <section class="card" aria-labelledby="award-title">
      <div class="card__header"><h2 class="card__title" id="award-title">{{ award.program }} scholarship</h2><span class="pill pill--success">{% icon "circle-check" %}Active</span></div>
      <dl class="details">
        <dt>Tier</dt><dd>{{ award.tier }}</dd>
        <dt>Allowance per term</dt><dd class="num">{{ award.amount|peso }}</dd>
        <dt>Next release</dt><dd><time datetime="2026-11-14">14 November 2026</time></dd>
        <dt>To renew</dt><dd>Keep a GWA of 80% or better with at least 15 units</dd>
      </dl>
    </section>
    <section class="card" aria-labelledby="apps-title">
      <div class="card__header"><h2 class="card__title" id="apps-title">Applications</h2><a href="#">Find programs</a></div>
      <div class="table-wrap" role="region" aria-labelledby="apps-title" tabindex="0">
        <table class="table">
          <thead><tr><th scope="col">Program</th><th scope="col">Submitted</th><th scope="col">Status</th></tr></thead>
          <tbody>{% for item in applications %}<tr><th scope="row"><a href="#">{{ item.program }}</a></th><td>{{ item.submitted }}</td><td><span class="pill pill--{{ item.tone }}">{% icon item.icon %}{{ item.label }}</span></td></tr>{% endfor %}</tbody>
        </table>
      </div>
    </section>
    <section class="card" aria-labelledby="money-title">
      <div class="card__header"><h2 class="card__title" id="money-title">Allowances</h2></div>
      <div class="table-wrap" role="region" aria-labelledby="money-title" tabindex="0">
        <table class="table">
          <thead><tr><th scope="col">Term</th><th scope="col" class="num">Amount</th><th scope="col">Status</th></tr></thead>
          <tbody>{% for item in allowances %}<tr><th scope="row">{{ item.term }}</th><td class="num">{{ item.amount|peso }}</td><td><span class="pill pill--{{ item.tone }}">{% icon item.icon %}{{ item.label }}</span></td></tr>{% endfor %}</tbody>
        </table>
      </div>
    </section>
  </div>
  <div class="stack">
    <section class="card" aria-labelledby="profile-title">
      <h2 class="card__title" id="profile-title">Your profile</h2>
      <div class="meter-row"><label for="profile-meter">85% complete</label><meter id="profile-meter" min="0" max="100" value="85">85%</meter></div>
      <p>Add your family's yearly income so programs can check if you qualify.</p>
      <a class="btn btn--secondary" href="#">{% icon "pencil" %}Complete your profile</a>
    </section>
    <section class="card" aria-labelledby="notices-title">
      <h2 class="card__title" id="notices-title">Notifications</h2>
      <ul class="list">{% for item in notices %}<li><p>{{ item.text }}</p><p class="text-sm text-muted">{{ item.when }}</p></li>{% endfor %}</ul>
    </section>
  </div>
</div>
{% endblock %}
```

`apps/kit/templates/kit/mockups/apply.html`:
```django
{% extends "layouts/student.html" %}{% load ui %}
{% block title %}Apply to LANI{% endblock %}
{% block content %}
{% include "components/breadcrumbs.html" %}
<div class="page-header">
  <div><h1>Apply to LANI</h1><p class="page-header__meta">Applications close on 15 November 2026</p></div>
</div>
<ol class="steps" aria-label="Application progress">
  <li class="steps__item steps__item--done"><span class="steps__marker">{% icon "check" %}</span>Profile<span class="visually-hidden"> (done)</span></li>
  <li class="steps__item steps__item--current" aria-current="step"><span class="steps__marker">2</span>Documents</li>
  <li class="steps__item"><span class="steps__marker">3</span>Review</li>
  <li class="steps__item"><span class="steps__marker">4</span>Submit</li>
</ol>
<div class="split">
  <div class="stack">
    <section class="card" aria-labelledby="docs-title">
      <h2 class="card__title" id="docs-title">Required documents</h2>
      <p class="text-muted">PDF, JPG or PNG, up to 10 MB each. Only staff reviewing your application can open them.</p>
      {% for doc in documents %}{% include "components/file_input.html" with id=doc.id name=doc.id label=doc.label help=doc.help state=doc.state progress=doc.progress filename=doc.filename error=doc.error %}{% endfor %}
    </section>
    <section class="card" aria-labelledby="declare-title">
      <h2 class="card__title" id="declare-title">Declaration</h2>
      {% field form.declaration %}
      <div class="btn-row">
        <button type="button" class="btn btn--primary">Submit application</button>
        <button type="button" class="btn btn--secondary">Save draft</button>
      </div>
    </section>
  </div>
  <div class="stack">
    <section class="card" aria-labelledby="program-title">
      <h2 class="card__title" id="program-title">About LANI</h2>
      <dl class="details">
        <dt>For</dt><dd>College students from Taguig in any recognized school</dd>
        <dt>Allowance</dt><dd class="num">₱5,000.00 to ₱10,000.00 a term, by tier</dd>
        <dt>Closes</dt><dd>15 November 2026</dd>
      </dl>
    </section>
    <section class="card" aria-labelledby="match-title">
      <h2 class="card__title" id="match-title">Do you qualify?</h2>
      <ul class="checklist">{% for rule in rules %}<li class="is-{{ rule.state }}">{% icon rule.icon %}<div><p>{{ rule.text }}</p><p class="text-sm text-muted">{{ rule.status }}</p></div></li>{% endfor %}</ul>
    </section>
  </div>
</div>
{% endblock %}
```

`apps/kit/templates/kit/mockups/application_review.html`:
```django
{% extends "layouts/staff.html" %}{% load ui %}
{% block title %}{{ applicant.name }}, application{% endblock %}
{% block content %}
<div class="page-header">
  <div><h1>{{ applicant.name }}</h1><p class="page-header__meta">Application APP-2026-0147 to {{ program.name }}, submitted <time datetime="2026-10-02">2 October 2026</time></p></div>
  <span class="pill pill--info">{% icon "file-text" %}Under review</span>
</div>
{% include "components/tabs.html" with tabs_label="Application sections" %}
<div class="split">
  <div class="stack">
    <section class="card" aria-labelledby="applicant-title">
      <h2 class="card__title" id="applicant-title">Applicant</h2>
      <dl class="details">
        <dt>School</dt><dd>{{ applicant.school }}</dd>
        <dt>Course and year</dt><dd>{{ applicant.course }}</dd>
        <dt>GWA</dt><dd>{{ applicant.gwa }}</dd>
        <dt>Family income</dt><dd class="num">{{ applicant.income|peso }} a year</dd>
        <dt>Barangay</dt><dd>{{ applicant.barangay }}</dd>
      </dl>
    </section>
    <section class="card" aria-labelledby="documents-title">
      <div class="card__header"><h2 class="card__title" id="documents-title">Documents</h2><p class="text-sm text-muted">2 of 4 approved</p></div>
      <div class="table-wrap" role="region" aria-labelledby="documents-title" tabindex="0">
        <table class="table">
          <thead><tr><th scope="col">Document</th><th scope="col">Status</th><th scope="col"><span class="visually-hidden">Actions</span></th></tr></thead>
          <tbody>{% for doc in documents %}<tr>
            <th scope="row">{{ doc.label }}<br><a class="text-sm" href="#">{% icon "download" %}{{ doc.file }}</a></th>
            <td><span class="pill pill--{{ doc.tone }}">{% icon doc.icon %}{{ doc.status }}</span></td>
            <td><div class="btn-row"><button type="button" class="btn btn--secondary">Approve</button><button type="button" class="btn btn--ghost">Decline</button></div></td>
          </tr>{% endfor %}</tbody>
        </table>
      </div>
    </section>
    <section class="card" aria-labelledby="eligibility-title">
      <h2 class="card__title" id="eligibility-title">Eligibility</h2>
      <ul class="checklist">{% for rule in rules %}<li class="is-{{ rule.state }}">{% icon rule.icon %}<div><p>{{ rule.text }}</p><p class="text-sm text-muted">{{ rule.status }}</p></div></li>{% endfor %}</ul>
      <div class="alert" role="note">{% icon "info" %}<div><p class="alert__title">Legacy model suggests: Priority tier</p><p>Advisory only. The rules above decide eligibility.</p></div></div>
    </section>
  </div>
  <div class="stack">
    <section class="card" aria-labelledby="decision-title">
      <h2 class="card__title" id="decision-title">Decision</h2>
      {% field decision_form.tier %}
      {% field decision_form.note %}
      <div class="btn-row">
        <button type="button" class="btn btn--primary">{% icon "check" %}Approve</button>
        <button type="button" class="btn btn--secondary">Return to applicant</button>
        <button type="button" class="btn btn--danger">Reject</button>
      </div>
    </section>
    <section class="card" aria-labelledby="history-title">
      <h2 class="card__title" id="history-title">History</h2>
      <ol class="timeline">{% for event in history %}<li><p class="timeline__what">{{ event.what }}</p><p class="timeline__when"><time datetime="{{ event.datetime }}">{{ event.when }}</time> by {{ event.who }}</p></li>{% endfor %}</ol>
    </section>
  </div>
</div>
{% endblock %}
```

`apps/kit/templates/kit/mockups/disbursements.html`:
```django
{% extends "layouts/staff.html" %}{% load ui %}
{% block title %}Disbursements{% endblock %}
{% block content %}
<div class="page-header">
  <div><h1>Disbursements</h1><p class="page-header__meta">{{ program.name }}, 1st semester 2026–2027</p></div>
  <button type="button" class="btn btn--secondary">{% icon "plus" %}Generate disbursements</button>
</div>
{% include "components/tabs.html" with tabs_label="Money sections" %}
<div class="stats">
  {% include "components/stat_tile.html" with label="Budget for 2026" value=budget.total|peso icon="wallet" tone="info" hint="January to December" %}
  {% include "components/stat_tile.html" with label="Released" value=budget.released|peso icon="banknote" tone="success" %}
  {% include "components/stat_tile.html" with label="Approved, not yet released" value=budget.committed|peso icon="hand-coins" tone="warning" %}
  {% include "components/stat_tile.html" with label="Available" value=budget.available|peso icon="wallet" tone="brand" %}
</div>
<div class="card meter-row">
  <label for="budget-used">Budget used</label>
  <meter id="budget-used" min="0" max="100" low="70" high="90" optimum="0" value="{{ budget.used_percent }}">{{ budget.used_percent }}%</meter>
  <p class="num">{{ budget.used_percent }}% of {{ budget.total|peso }}, counting approved disbursements</p>
</div>
<form class="filters" method="get" action="" role="search" aria-label="Filter disbursements">
  <div class="field"><label class="field__label" for="d-q">Scholar</label><input class="input" type="search" id="d-q" name="q"></div>
  <div class="field"><label class="field__label" for="d-status">Status</label><select class="input" id="d-status" name="status"><option>Any status</option><option>Prepared</option><option>Approved</option><option>Released</option></select></div>
  <div class="field"><label class="field__label" for="d-tier">Tier</label><select class="input" id="d-tier" name="tier"><option>Any tier</option><option>Basic</option><option>Priority</option><option>Honors</option></select></div>
  <button class="btn btn--secondary" type="submit">{% icon "filter" %}Apply filters</button>
</form>
<form method="post" action="" data-bulk>
  {% csrf_token %}
  <div class="bulk-bar" data-bulk-bar>
    <p class="bulk-bar__count" data-bulk-count aria-live="polite">Select disbursements, then choose an action.</p>
    <div class="btn-row">
      <button class="btn btn--primary" type="button">Approve selected</button>
      <button class="btn btn--secondary" type="button">{% icon "shield-check" %}Release selected</button>
    </div>
  </div>
  <p class="table-count">{{ total }} disbursements. Releasing needs a program head and asks for your password again.</p>
  <div class="table-wrap" role="region" aria-labelledby="disbursements-caption" tabindex="0">
    <table class="table">
      <caption id="disbursements-caption" class="visually-hidden">Disbursements</caption>
      <thead><tr><th scope="col" class="select"><input type="checkbox" data-bulk-all aria-label="Select all disbursements"></th><th scope="col">Scholar</th><th scope="col">Tier</th><th scope="col" class="num">Amount</th><th scope="col">Status</th></tr></thead>
      <tbody>{% for row in page %}<tr>
        <td class="select"><input type="checkbox" name="ids" value="{{ row.id }}" data-bulk-item aria-label="Select {{ row.name }}"></td>
        <th scope="row">{{ row.name }}</th><td>{{ row.tier }}</td><td class="num">{{ row.amount|peso }}</td>
        <td><span class="pill pill--{{ row.tone }}">{% icon row.icon %}{{ row.label }}</span></td>
      </tr>{% endfor %}</tbody>
    </table>
  </div>
</form>
{% pagination page %}
{% endblock %}
```

`apps/kit/templates/kit/mockups/office_dashboard.html`:
```django
{% extends "layouts/office.html" %}{% load ui %}
{% block title %}Overview{% endblock %}
{% block content %}
<div class="page-header">
  <div><h1>Overview</h1><p class="page-header__meta">All programs, school year 2026–2027</p></div>
  <a class="btn btn--secondary" href="#">{% icon "download" %}Export report</a>
</div>
<div class="stats">
  {% include "components/stat_tile.html" with label="Programs" value="2" icon="school" tone="info" hint="1 accepting applications" %}
  {% include "components/stat_tile.html" with label="Active scholars" value="1,284" icon="users" tone="brand" hint="38 more than last term" %}
  {% include "components/stat_tile.html" with label="Applications waiting" value="96" icon="file-text" tone="warning" hint="12 waiting over 7 days" %}
  {% include "components/stat_tile.html" with label="Released this year" value="₱18,240,000.00" icon="banknote" tone="success" %}
</div>
<div class="split">
  <div class="stack">
    <section class="card" aria-labelledby="programs-title">
      <div class="card__header"><h2 class="card__title" id="programs-title">Programs</h2><a href="#">Manage programs</a></div>
      <div class="table-wrap" role="region" aria-labelledby="programs-title" tabindex="0">
        <table class="table">
          <thead><tr><th scope="col">Program</th><th scope="col">Applications window</th><th scope="col" class="num">Applications</th><th scope="col" class="num">Scholars</th><th scope="col">Budget used</th></tr></thead>
          <tbody>{% for item in programs %}<tr>
            <th scope="row"><a href="#">{{ item.name }}</a></th><td>{{ item.window }}</td>
            <td class="num">{{ item.applications }}</td><td class="num">{{ item.scholars }}</td>
            <td><div class="meter-row"><meter min="0" max="100" low="70" high="90" optimum="0" value="{{ item.used_percent }}" aria-label="{{ item.name }} budget used">{{ item.used_percent }}%</meter><p class="num">{{ item.used_percent }}%</p></div></td>
          </tr>{% endfor %}</tbody>
        </table>
      </div>
    </section>
    <section class="card" aria-labelledby="months-title">
      <h2 class="card__title" id="months-title">Applications by month</h2>
      <div class="table-wrap" role="region" aria-labelledby="months-title" tabindex="0">
        <table class="table">
          <thead><tr><th scope="col">Month</th><th scope="col" class="num">Applications</th><th scope="col"><span class="visually-hidden">Relative volume</span></th></tr></thead>
          <tbody>{% for month in months %}<tr><th scope="row">{{ month.label }}</th><td class="num">{{ month.count }}</td><td><meter min="0" max="{{ max_month }}" value="{{ month.count }}" aria-label="{{ month.label }}: {{ month.count }} applications">{{ month.count }}</meter></td></tr>{% endfor %}</tbody>
        </table>
      </div>
    </section>
  </div>
  <div class="stack">
    <section class="card" aria-labelledby="attention-title">
      <h2 class="card__title" id="attention-title">Needs attention</h2>
      <ul class="checklist">{% for item in attention %}<li class="is-pending">{% icon item.icon %}<div><p><a href="#">{{ item.text }}</a></p></div></li>{% endfor %}</ul>
    </section>
    <section class="card" aria-labelledby="activity-title">
      <h2 class="card__title" id="activity-title">Recent activity</h2>
      <ol class="timeline">{% for event in activity %}<li><p class="timeline__what">{{ event.what }}</p><p class="timeline__when"><time datetime="{{ event.datetime }}">{{ event.when }}</time></p></li>{% endfor %}</ol>
    </section>
  </div>
</div>
{% endblock %}
```

The disbursements filter `<form>` and bulk `<form>` use `action=""`. The filter is a GET to the same mockup, which is
harmless. The bulk buttons are `type="button"`, so the mockup never POSTs.

- [ ] **Step 6: Build and run all the tests**

```powershell
npm --prefix frontend run build
python -m uv run pytest -n auto
python -m uv run pytest -m e2e --ds=config.e2e_settings --browser chromium
python -m uv run ruff check .; python -m uv run ruff format --check .; python -m uv run mypy .
npm --prefix frontend run typecheck; npm --prefix frontend run check; npm --prefix frontend run budget
```
Expected: all PASS. A phone-width overflow failure means a component needs `min-width: 0` or a `.table-wrap`. Fix
the CSS rather than the test.

- [ ] **Step 7: Commit**

```powershell
git add apps/kit tests/e2e/test_mockups.py
git commit -m "feat: add key-screen mockups for the M3 approval gate"
```

---

## Finish: verification, review and the mockup gate

- [ ] **Every CI command, as CI runs it** (`DJANGO_ENV_FILE=/nonexistent` plus CI's env vars, so the local `.env`
  can't mask anything):
  - ruff check and format, mypy, `makemigrations --check`;
  - `check --deploy --fail-level WARNING` with `DJANGO_DEBUG=false` and `DJANGO_ALLOWED_HOSTS=scholarsync.example`;
  - `pytest -n auto`, then the e2e command;
  - the front-end typecheck, check, build and budget.

  Record the test counts and the budget figure.
- [ ] **Whole-branch review:** dispatch a fresh reviewer over `07ac387..HEAD`, with this plan, spec §10/§12 and the
  Review Focus list. Fix Critical and Important findings test-first (one `fix:` commit each); log Minor ones as known issues.
- [ ] **Screenshots for Kenneth:** run the mockup e2e test with `MOCKUP_SCREENSHOTS` set to the session scratchpad.
  That gives phone and desktop PNGs of all five screens.
- [ ] **The gate:**
  - ask Kenneth to review `/_kit/mockups/` (`python -m uv run python manage.py runserver` with `DJANGO_KIT=true`;
    the screenshots are attached);
  - feedback becomes `fix:`/`feat:` commits in Task 9's files (or the component CSS), re-verified by the same tests;
  - when Kenneth approves, mark the key-screen mockups approved and M3 done.
- [ ] **Push:** only when Kenneth asks. The new `e2e` CI job runs for the first time on that push.
