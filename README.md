# Playwright AP Website Automation Framework

A production-grade E2E web automation and visual regression testing framework built with Python, Playwright, Pytest, and Claude AI diagnostics.

Target Application: [https://apolskiy.github.io/](https://apolskiy.github.io/)

---

## Key Features

- **Page Object Model (POM):** Clean separation of UI locators, interaction workflows, and assertion logic. Test modules contain zero raw selectors and never touch a Playwright `Page` directly.
- **Dynamic Site Discovery:** An async Playwright crawler maps the site's route graph at collection time and writes `reports/sitemap.json`. Every discovered route is then parameterised into its own health-check tests, so publishing a new page grows the suite with no test edit.
- **Cross-Viewport Coverage:** Every layout rule is asserted on both sides of the site's `max-width: 600px` breakpoint — desktop (1920x1080) and mobile (390x844).
- **Event-Driven CI/CD Execution:** Runs on GitHub Actions on push, on a weekly schedule, and on a `repository_dispatch` fired by the target repository (`apolskiy.github.io`) whenever its `.html`, `.css`, or `.js` sources deploy.
- **Dual Reporting Engines:** Rich interactive **Allure HTML** reports plus standalone **Pytest HTML** execution summaries.
- **AI-Powered Test Diagnostics:** On any failure the suite attaches a screenshot and a DOM snapshot, then asks Claude to classify the failure and propose a fix — attached to the Allure report as a structured triage note.
- **Clean Code & Static Analysis:** PEP 8 compliance, Google-style docstrings, and strict type annotations, gated at **Pylint 10.00/10** in CI.

---

## Project Architecture

```text
PlaywrightAPWebsiteAutomation/
├── .github/
│   └── workflows/
│       └── run_tests.yml          # Pylint gate + E2E job, event- and cron-driven
├── config/
│   ├── __init__.py
│   └── settings.py                # Environment loader, viewport and timeout constants
├── pages/
│   ├── __init__.py
│   ├── base_page.py               # Navigation, viewport, DOM capture, layout measurement
│   ├── landing_page.py            # POM + NavigationTab enum for the portfolio page
│   └── route_page.py              # Generic POM for any crawler-discovered route
├── utils/
│   ├── __init__.py
│   ├── claude_inspector.py        # Claude API failure triage helper
│   ├── site_crawler.py            # Async sitemap crawler and route discovery engine
│   └── visual_comparator.py       # Pillow image diff visual testing helper
├── tests/
│   ├── __init__.py
│   ├── test_navigation.py         # Header integrity and SPA routing
│   ├── test_responsive.py         # Desktop/mobile layout validation
│   ├── test_link_obfuscation.py   # Base64 anti-scraping link and e-mail decoding
│   ├── test_link_styling.py       # Shared interactive link hover styling
│   └── test_dynamic_routes.py     # Health checks generated per discovered route
├── conftest.py                    # Viewport fixtures + AI failure-diagnostics hook
├── .env.example                   # Template for local configuration
├── .gitignore
├── .pylintrc                      # Static analysis configuration
├── pytest.ini                     # Pytest, Allure, & browser runtime flags
├── README.md
└── requirements.txt
```

---

## Quick Start

Requires **Python 3.10+**; developed, verified, and CI-pinned on **3.14**.

```bash
pip install -r requirements.txt
python -m playwright install chromium

cp .env.example .env      # optional; sensible defaults apply without it
python -m pytest
```

Run against another engine, or all three:

```bash
python -m pytest --browser=firefox
python -m pytest --browser=chromium --browser=firefox --browser=webkit
python -m pytest --headed --slowmo 250          # watch a run locally
```

> `--browser` is intentionally absent from `pytest.ini`. `pytest-playwright` treats the flag as repeatable, so a value in `addopts` would be additive rather than overridable — `--browser=firefox` would run Chromium *and* Firefox. Chromium is already the plugin default, so omitting it keeps the default run identical while letting the command line select the engine outright.

---

## Configuration

All configuration is read once, at session start, by `config.settings.Settings`. Test modules never read `os.environ`.

| Variable | Default | Purpose |
| --- | --- | --- |
| `BASE_URL` | `https://apolskiy.github.io/` | Application under test |
| `EXPECT_TIMEOUT_MS` | `10000` | Ceiling for auto-retrying web-first assertions |
| `AI_DIAGNOSTICS_ENABLED` | `false` | Master switch for Claude failure triage |
| `ANTHROPIC_API_KEY` | *(unset)* | Credential for the diagnostics hook |
| `CLAUDE_MODEL` | `claude-opus-5` | Model used for failure triage |

Diagnostics activate only when `AI_DIAGNOSTICS_ENABLED` is truthy **and** a key is present, so a fork without secrets runs green.

---

## Test Design Principles

**Locators.** Accessible locators (`get_by_role`, `get_by_text`) are used wherever the markup exposes a role or an accessible name. The application ships no `data-testid` attributes, so the tab panels — plain `<div>` elements carrying only an `id` — are addressed by a flat `#id` selector. Structural chains such as `div > ul > li:nth-child(2)` are never used.

**Synchronisation.** There are no `wait_for_timeout` calls anywhere in the suite. The page decorates itself from a `DOMContentLoaded` listener, and readiness is expressed as an exact web-first assertion: the suite waits for the `span.enc-link` placeholder collection to drain to zero. Layout measurements settle the DOM with a visibility assertion before reading any bounding box.

**Assertions.** Checks that depend on DOM internals invisible to a test author — the `active` class toggled by the SPA router, the `mailto:` payload produced by the anti-scraping decoder — are published by the Page Object as `expect_*` helpers built on Playwright's retrying assertions. Everything else is exposed as a `Locator` so tests assert on it directly.

**Isolation.** Every test gets its own browser context with an explicit viewport, so tests can run in any order without cookie, storage, or window-size bleed.

---

## Dynamic Site Discovery

`utils/site_crawler.py` implements `SiteMapCrawler`, an asynchronous breadth-first Playwright crawler.

It renders each page in a real browser rather than fetching raw HTML — **this is required, not a preference**: the site publishes every outbound link as a base64 payload that only becomes an `<a href>` after its `DOMContentLoaded` script runs, so a `requests`-based crawler would discover nothing.

**Discovery rules**

| Accepted | Rejected |
| --- | --- |
| Relative paths (`/about`) | External hosts |
| Bare fragments (`#projects`), resolved against the current page | `mailto:`, `tel:`, `javascript:`, `data:`, `file:`, `ftp:` |
| Internal absolute URLs | Assets: `.pdf`, `.zip`, `.png`, `.css`, `.js`, fonts, media, Office documents |

URLs are canonicalised before use, so an empty path and `/` collapse to one route — the site links to itself both ways, which would otherwise produce a duplicate. Traversal is bounded by `max_depth` (3) and `max_pages` (50) so a link cycle cannot hang collection, and a route that fails to navigate is still recorded with `status_code: 0` rather than vanishing.

**Artifact** — `reports/sitemap.json`. Route records carry exactly the four specified fields; the surrounding envelope adds crawl context and any unhandled JavaScript exceptions caught via `pageerror` during the walk:

```json
{
  "base_url": "https://apolskiy.github.io/",
  "generated_at": "2026-07-29T06:07:33+00:00",
  "route_count": 1,
  "routes": [
    { "url": "https://apolskiy.github.io/", "parent_route": "", "discovered_at": "...", "status_code": 200 }
  ],
  "javascript_errors": []
}
```

**Parameterisation** — `tests/test_dynamic_routes.py` implements `pytest_generate_tests`, which resolves the route list once per session (memoised, since the hook fires per test function) and parameterises five health checks across it: HTTP 200, a clean console/network/JavaScript log, a visible and non-empty DOM root, and no horizontal overflow at either viewport. Test ids are the route paths, so a failure reads as `test_route_responds_with_http_200[/about.html-chromium]`.

```bash
python -m pytest                        # re-crawls during collection
python -m pytest --use-cached-sitemap   # reuses reports/sitemap.json
```

CI should re-crawl so a newly published page is discovered; the cache flag is a local-iteration convenience.

> **Current scope:** the live site is a single-document SPA whose tab router uses `<li data-tab>` elements rather than anchors, and every decoded link points off-site. Discovery therefore yields **one** route today. The engine was verified against a two-page fixture: adding a linked page generated five new test cases automatically, and adding a link to a non-existent page produced a failing `HTTP 404` check naming the parent route it was discovered from.

---

## Reporting

```bash
python -m pytest                       # writes allure-results/ and reports/
allure serve allure-results            # interactive Allure report
```

Every test carries `@allure.epic`, `@allure.feature`, `@allure.story`, and `@allure.severity`, and each phase is wrapped in an `allure.step` — including the steps emitted by the Page Object itself, so the report reads as a narrative of the user journey rather than a list of clicks.

On failure the suite attaches:

1. A full-page **screenshot** at the moment of failure.
2. The fully rendered **DOM snapshot**, including script-injected nodes.
3. A **Claude root-cause analysis** — verdict (`application regression` / `test defect` / `environment flake` / `inconclusive`), the DOM evidence behind it, the probable cause, and a suggested fix.

The diagnostics hook is strictly advisory. A missing credential, a network failure, or an API error is logged as a warning and degrades to "no report" — it never converts a product failure into an infrastructure failure, and never masks the real Playwright error.

---

## Static Analysis

```bash
python -m pylint config pages utils tests conftest.py
```

The suite is held at **10.00/10**, and CI runs the same command with `--fail-under=10` before any browser starts. `.pylintrc` rejects one- and two-character identifiers outright rather than allowing the usual `i`/`x`/`df` escape hatches. Only two checks are disabled, each for a documented reason: `redefined-outer-name` (the pytest fixture idiom) and `duplicate-code` (test suites intentionally repeat arrange/assert shapes).

---

## Defect Found and Fixed

`test_mobile_layout_has_no_horizontal_overflow` caught a real mobile layout bug on its first run: at a 390px viewport the document measured **398px**, and one tab reached **400px**. Two independent causes in the `max-width: 600px` block of `css/apolskiybiz.css`:

1. **Profile header (all tabs, +8px).** `#profile-header table.layout td` was set to `display: block; width: 100%` but never given `box-sizing: border-box`, so the scoped 10px horizontal cell padding was added *on top of* the 100% width. The stacked data-table cells in the same media query already declared `box-sizing`; the profile-header cells were missed.
2. **HTTP Emulators tab (+10px).** Long unbreakable tokens — source filenames such as `custom_header_response_to_http_request.py` — set the table's intrinsic minimum content width, and a `<table>` box grows to that minimum regardless of `width: 100%`.

Both are fixed in the site repository (`apolskiy/apolskiy.github.io`). The second needed `overflow-wrap: anywhere` specifically: `break-word` permits a mid-word break but does **not** reduce the intrinsic min-content size that the table is sized from, so it would not have shrunk the table.

Verified clean afterwards on every tab at 320px, 390px, and 600px, on both Chromium and Firefox.

> The suite runs against the live URL, so this test stays red until the CSS change is deployed to GitHub Pages.

---

## Coverage Summary

| Suite | Scenarios | Focus |
| --- | --- | --- |
| `test_navigation.py` | 10 | Title, profile header, footer, default tab, per-tab panel exclusivity, tab deselection, persistent chrome, skills matrix |
| `test_responsive.py` | 7 | Tab-strip wrapping, header suppression below the breakpoint, horizontal overflow on both viewports, stacked profile header |
| `test_link_obfuscation.py` | 6 | Placeholder decoding, absolute/safe URL schemes, `noopener noreferrer` hardening, address never rendered as text, copyright owner link, `noscript` fallback |
| `test_link_styling.py` | 1 | Copyright link shares the table hover colour, and hovering visibly changes it |
| `test_dynamic_routes.py` | 5 × routes | Per discovered route: HTTP 200, console/network/JS error log, visible DOM root, desktop and mobile overflow |

**29 tests** against the live site today (5 dynamic × 1 discovered route), growing automatically as pages are published.
