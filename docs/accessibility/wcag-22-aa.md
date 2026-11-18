# WCAG 2.2 AA review

ScholarSync aims for WCAG 2.2 level AA (spec §12). This record was made on 2026-11-18 against `main`. It has two
halves:

- **Automated:** `tests/e2e/test_accessibility.py` runs axe-core 4.10.3 (tags `wcag2a`, `wcag2aa`, `wcag21a`,
  `wcag21aa`, `wcag22aa`) on 31 key screens across the five roles, at 1280 and 375 px wide. Any violation fails CI.
  The same file checks reflow at 320 px and a keyboard-only sign-in.
- **By hand:** the criteria axe can't judge are checked by reading the templates and using the screens with keyboard,
  zoom and a screen reader's accessibility tree (Chromium devtools). The evidence column says which.

**Statuses:** Met (with evidence), Not applicable (with the reason) or Gap (listed again under "Open gaps").
WCAG 2.2 removed 4.1.1 Parsing, so it has no row.

## Level A

| Criterion | Status | Evidence |
|---|---|---|
| 1.1.1 Non-text Content | Met | axe `image-alt`, `svg-img-alt`, `button-name`, `link-name`; icons are `aria-hidden` sprites (`apps/core/templatetags/ui.py` `icon`), each icon-only button has an `aria-label` (the bell in `templates/layouts/app.html`) |
| 1.2.1 Audio-only and Video-only | Not applicable | No audio or video |
| 1.2.2 Captions (Prerecorded) | Not applicable | No video |
| 1.2.3 Audio Description or Media Alternative | Not applicable | No video |
| 1.3.1 Info and Relationships | Met | axe `label`, `th-has-data-cells`, `list`, `definition-list`, `aria-*`; tables use `th scope` (`apps/core/tests/test_table_tags.py`); fields render through `{% field %}` with labels and `aria-describedby` (`apps/core/tests/test_field_tag.py`) |
| 1.3.2 Meaningful Sequence | Met | Source order matches visual order: the layouts place the top bar before the sidebar for phones (`templates/layouts/app.html` comment); checked by Tab order on the key screens |
| 1.3.3 Sensory Characteristics | Met | Instructions name things by label, never by shape or position (copy review of the screens and the information pages) |
| 1.4.1 Use of Color | Met | Status is bold text, never colour alone (spec §12; `{% status %}`); links are underlined in body text |
| 1.4.2 Audio Control | Not applicable | No audio |
| 2.1.1 Keyboard | Met | `tests/e2e/test_accessibility.py::test_keyboard_only_sign_in`; dialogs, drawers, menus and the nav toggle are native `<dialog>`, `<details>` and buttons (`tests/e2e/test_overlays.py`) |
| 2.1.2 No Keyboard Trap | Met | Native `<dialog>` closes on Escape and returns focus (`tests/e2e/test_overlays.py`) |
| 2.1.4 Character Key Shortcuts | Not applicable | No single-key shortcuts |
| 2.2.1 Timing Adjustable | Gap | Sessions end 12 hours after sign-in (`SESSION_COOKIE_AGE`, `config/settings.py`) with no warning; see Open gaps |
| 2.2.2 Pause, Stop, Hide | Met | Toasts are short and dismissible; nothing moves or auto-updates for more than 5 s (`frontend/src/toast.ts`) |
| 2.3.1 Three Flashes | Met | No flashing content |
| 2.4.1 Bypass Blocks | Met | "Skip to content" link first in `templates/base.html`; landmarks (`apps/core/tests/test_layouts.py`) |
| 2.4.2 Page Titled | Met | Every page sets `{% block title %}` ("… · City of Taguig", `templates/base.html`); axe `document-title` |
| 2.4.3 Focus Order | Met | Tab order follows reading order on the key screens (checked by hand; `test_keyboard_only_sign_in`) |
| 2.4.4 Link Purpose (In Context) | Met | Links name their target; repeated actions carry a visually hidden object ("Done: {task}", `templates/workspace/tasks/list.html`) |
| 2.5.1 Pointer Gestures | Met | No path-based or multipoint gestures |
| 2.5.2 Pointer Cancellation | Met | Native buttons and links fire on release |
| 2.5.3 Label in Name | Met | axe `label-content-name-mismatch` (experimental, checked by hand on icon buttons: "Notifications", "Menu") |
| 2.5.4 Motion Actuation | Not applicable | No motion input |
| 3.1.1 Language of Page | Met | `<html lang="en">` (`templates/base.html:2`); axe `html-has-lang` |
| 3.2.1 On Focus | Met | Focus never submits or navigates |
| 3.2.2 On Input | Met | Filters submit with a button; selects never navigate on change |
| 3.2.6 Consistent Help | Met | The footer's Help and Contact links sit in the same place on every layout (`apps/core/tests/test_pages.py::test_every_layout_has_the_footer_and_no_affiliation_claim`) |
| 3.3.1 Error Identification | Met | Field errors in text next to the field with `aria-invalid` and a form error summary (`templates/components/form_errors.html`, `apps/core/tests/test_field_tag.py`) |
| 3.3.2 Labels or Instructions | Met | Every input has a visible label and help text where the format matters (dates, files: `components/file_input.html`) |
| 3.3.7 Redundant Entry | Met | Re-sending a returned report or application keeps what was entered (`templates/reports/staff_detail.html` prefilled form) |
| 4.1.2 Name, Role, Value | Met | axe `aria-*`, `button-name`, `select-name`; native controls throughout |

## Level AA

| Criterion | Status | Evidence |
|---|---|---|
| 1.2.4 Captions (Live) | Not applicable | No live media |
| 1.2.5 Audio Description (Prerecorded) | Not applicable | No video |
| 1.3.4 Orientation | Met | No orientation lock; layouts reflow at any width (`test_reflow_at_320px`) |
| 1.3.5 Identify Input Purpose | Met | `autocomplete` on personal fields (`apps/students/forms.py:69`) and allauth's email and password fields |
| 1.4.3 Contrast (Minimum) | Met | `tests/test_tokens.py::test_text_pairs_reach_aa`; axe `color-contrast` on every key screen |
| 1.4.4 Resize Text | Met | Sizes in rem; at 200 % zoom (a 640 px viewport) pages reflow without loss (the 375 px axe pass) |
| 1.4.5 Images of Text | Met | No images of text; the logo is an SVG mark beside a text wordmark |
| 1.4.10 Reflow | Met | `tests/e2e/test_accessibility.py::test_reflow_at_320px` (tables scroll inside their own region, which 1.4.10 allows) |
| 1.4.11 Non-text Contrast | Met | `tests/test_tokens.py::test_non_text_pairs_reach_3_to_1` (input borders, focus ring); button outlines rely on their text label |
| 1.4.12 Text Spacing | Met | No fixed heights on text containers; line height 1.5 (spec §12) |
| 1.4.13 Content on Hover or Focus | Met | No hover-only content; menus are `<details>` opened by click and closed by Escape |
| 2.4.5 Multiple Ways | Met | Navigation plus search on staff and office pages and lists with filters; the student area is small enough to reach in two steps |
| 2.4.6 Headings and Labels | Met | One `h1` per page (`tests/e2e/test_office_insights.py`, `test_office_flow.py`); axe `heading-order`, `empty-heading` |
| 2.4.7 Focus Visible | Met | 3 px ink outline plus a yellow halo (spec §12 tokens); `test_keyboard_only_sign_in` asserts a visible focus style |
| 2.4.11 Focus Not Obscured (Minimum) | Met | The only sticky parts are the desktop sidebar, in its own column (`frontend/src/styles/layouts.css:338`), and the drawer's header, inside the drawer (`frontend/src/styles/components/feedback.css:213`); neither covers the page's focused content |
| 2.5.7 Dragging Movements | Not applicable | No dragging |
| 2.5.8 Target Size (Minimum) | Met | Controls at least 32 px (spec §12); axe `target-size` (wcag22aa) |
| 3.1.2 Language of Parts | Met | All content is English |
| 3.2.3 Consistent Navigation | Met | One sidebar per area from `shell_context` (`apps/core/shell.py`), same order on every page |
| 3.2.4 Consistent Identification | Met | Shared components (`templates/components/`) give the same names to the same functions |
| 3.3.3 Error Suggestion | Met | Errors say how to fix ("The period must end on or after its start.", "Upload the report as a PDF.") |
| 3.3.4 Error Prevention (Legal, Financial, Data) | Met | Money and account changes ask for the password again (spec §10) and payouts are reviewed before release; submissions can be withdrawn |
| 3.3.8 Accessible Authentication (Minimum) | Met | Email and password with `autocomplete` so password managers fill them; paste allowed; Google sign-in for students |
| 4.1.3 Status Messages | Met | Toasts in an `aria-live="polite"` region (`templates/base.html:21`); upload progress in a live region (`components/file_input.html`) |

## Open gaps

- **2.2.1 Timing Adjustable** (larger): a session ends 12 hours after sign-in with no warning, so someone mid-form
  at that moment is sent to sign in and loses the post. Options: warn a few minutes before with a "Stay signed in"
  button (needs a small script and a keep-alive endpoint), or keep the session alive while the person is active
  (`SESSION_SAVE_EVERY_REQUEST`, at the cost of a write per request). The maintainer decides.
