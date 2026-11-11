"""The Page Object for the single-page portfolio at https://apolskiy.github.io/.

Created: 2026-07-28
Last updated: 2026-11-10

This file contains ``LandingPage``, the Page Object every landing-page test
drives; ``NavigationTab``, the enum declaring every published tab with its
label, panel ``id`` and panel heading; the two helpers ``soft_text_pattern``
and ``github_repository``; and the module constants naming the labels,
accessible names and URL shapes the page publishes.

The ``landing_page`` fixtures in ``conftest.py`` build a ``LandingPage`` per
test, and the test modules reach the DOM only through it, as locators,
state reads or ``expect_*`` assertions. A wrong locator here fails every test
that uses it at once, with a timeout rather than a wrong value. Three suites
parametrize over ``NavigationTab``, so adding a member adds their cases.
Auditing the page's links is delegated to ``LinkAuditor`` through the
``links`` attribute.

**Locators are accessible first.** Roles and accessible names are used where
the markup exposes them, a flat ``#id`` addresses the tab panels, and
structural chains are never used. Visible text is matched through
``soft_text_pattern``, which ignores letter case (the stylesheet already
upper-cases tab labels), whitespace and line wrapping, and extra words around
the label, while staying anchored on word boundaries so ``Web Site`` cannot
match ``Web Automation`` and a genuine relabeling is still caught.

**Tables are addressed by accessible name**, published as an ``aria-label``,
because the Home panel holds more than one table and an unqualified table role
would fail strict mode. The semantic class stays as a fallback: the mobile
stylesheet re-declares row and cell ``display``, which makes the computed table
role browser-dependent below the breakpoint, and it keeps the locator working
against a deployment older than the ``aria-label``.

**Project rows are matched by the full text of their first cell**, never by
position or by the row's whole text, so reordering a table cannot retarget a
locator and a row whose prose uses the word "documentation" is not taken for
the Documentation row.

**Repositories compare as lower-cased ``owner/name``.** Every reference a
project panel publishes (repository, badge, README) is a path under one
repository, and GitHub resolves owner and repository names case-insensitively,
so a difference in case is cosmetic rather than a panel pointing elsewhere.

**Tab panel ids carry the ordinal the tab was added in**, not its position, so
they do not renumber when a tab is inserted. Members are declared in strip
order, so a parametrized test reads in the order a visitor meets the tabs.

**Pointer and keyboard are one action.** ``open_project_from_evidence`` takes
an optional key rather than having a twin method, because the Evidence controls
carry a button role and a caller should not have to know which input a test
exercises.

**The portrait must be first party.** A portrait hosted elsewhere is an
availability risk the site does not control: a signed or expiring CDN URL
eventually stops resolving and breaks the page for every visitor.

Specified by ``README.md`` sections "Test Design Principles" (locator and
assertion policy), "Key Features" (link auditing kept out of the Page Object,
panels checked against themselves) and "Project Architecture" (``NavigationTab``
as the single declaration of a tab).
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Final
from urllib.parse import urlparse

import allure
from playwright.sync_api import Locator, Page, expect

from pages.base_page import BasePage
from utils.link_auditor import LinkAuditor

#: WHOLE TOKEN. Matches ``active`` inside a space-separated ``class`` attribute
#: and never a substring such as ``inactive``.
ACTIVE_CLASS_PATTERN: Final[re.Pattern[str]] = re.compile(r"(?:^|\s)active(?:\s|$)")

#: DECODED ADDRESS. The shape of the contact ``href``, such as
#: ``mailto:someone@example.com``.
MAILTO_PATTERN: Final[re.Pattern[str]] = re.compile(r"^mailto:[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")

#: DECODED LINK. The shape of an outbound ``href``.
HTTPS_URL_PATTERN: Final[re.Pattern[str]] = re.compile(r"^https://\S+$")

#: HIDDEN ADDRESS. The label rendered in place of the decoded address.
EMAIL_LINK_LABEL: Final[str] = "Email"

#: OWNER NAME. The portrait's accessible name, from its ``alt`` attribute.
PROFILE_NAME: Final[str] = "Aleksandr Polskiy"

#: ACCESSIBLE NAME (added 2026-07-29). The skills table's ``aria-label``.
SKILLS_MATRIX_LABEL: Final[str] = "Technical Skills Matrix"

#: ACCESSIBLE NAME (added 2026-07-29). The engineering-outcomes table's
#: ``aria-label``.
OUTCOMES_TABLE_LABEL: Final[str] = "Selected Engineering Outcomes"

#: ROW LABEL. The project-table row linking a project's documentation.
DOCUMENTATION_ROW_LABEL: Final[str] = "Documentation"

#: ROW LABEL. The project-table row naming the repositories a panel describes.
REPOSITORY_ROW_LABEL: Final[str] = "Repo"

#: GITHUB. The host serving every repository, badge and README a panel cites.
GITHUB_HOST: Final[str] = "github.com"

#: ROW LABEL. The project-table row carrying the build-status badges.
CI_STATUS_ROW_LABEL: Final[str] = "CI / Build Status"


def soft_text_pattern(text: str) -> re.Pattern[str]:
    """Return a tolerant matcher for a piece of visible text.

    The match ignores letter case, whitespace and line wrapping, and extra
    words around the text, and is anchored on word boundaries.

    Args:
        text (str): The expected visible text.

    Returns:
        re.Pattern[str]: A case-insensitive pattern in which each run of
        whitespace matches any whitespace, bounded by word boundaries.
    """
    spaced_words = r"\s+".join(re.escape(word) for word in text.split())
    return re.compile(rf"\b{spaced_words}\b", re.IGNORECASE)


def github_repository(url: str) -> str:
    """Return the ``owner/name`` repository a GitHub URL belongs to.

    The trailing path is discarded and the pair is lower-cased.

    Args:
        url (str): An absolute URL, which need not be a GitHub one.

    Returns:
        str: The lower-cased ``owner/name`` pair, or an empty string when the
        URL is not served by GitHub or names no repository.
    """
    parsed = urlparse(url)
    if parsed.netloc.lower() != GITHUB_HOST:
        return ""
    segments = [segment for segment in parsed.path.split("/") if segment]
    if len(segments) < 2:
        return ""
    return "/".join(segments[:2]).lower()


class NavigationTab(Enum):
    """Declare every tab the portfolio's single-page router publishes.

    Each member carries the tab's visible label, the ``id`` of the panel the
    router reveals, and the heading at the top of that panel. Home and
    Engineering Outcomes are the two tabs whose heading differs from the label,
    because they hold a cross-project table. Members are declared in the order
    of the navigation strip, and publishing a tab means adding a member here.
    """

    HOME = ("Home", "aphome1", "Technical Skills Matrix")
    ENGINEERING_OUTCOMES = (
        "Engineering Outcomes",
        "apoutcomes6",
        "Selected Engineering Outcomes",
    )
    REST_API = ("AI Assisted Rest API", "aprestapiclaude2", "AI Assisted Rest API")
    PORTFOLIO_WEBSITE = ("Portfolio Website", "apwebsite3", "Portfolio Website")
    WEB_AUTOMATION = ("Web Automation", "apwebtest4", "Web Automation")
    HTTP_EMULATORS = ("HTTP Emulators", "aphttpemulators5", "HTTP Emulators")
    VM_CLUSTER = (
        "VM Cluster Deployment",
        "apvmcluster7",
        "VM Cluster Deployment",
    )
    TEST_INSIGHTS = ("Test Insights", "apinsights8", "Test Insights")
    LLM_EVALUATION = ("Multi-LLM Evaluation", "apllmeval9", "Multi-LLM Evaluation")

    @property
    def label(self) -> str:
        """Return the visible text of the tab.

        Returns:
            str: The label exactly as it appears in the DOM. The stylesheet
            upper-cases it for display only, which does not affect matching.
        """
        return self.value[0]

    @property
    def panel_id(self) -> str:
        """Return the identifier of the panel this tab reveals.

        Returns:
            str: The ``id`` attribute of the tab's ``.tab-content`` element.
        """
        return self.value[1]

    @property
    def panel_heading(self) -> str:
        """Return the heading rendered at the top of this tab's panel.

        Returns:
            str: The exact heading text that proves the right panel was revealed.
        """
        return self.value[2]


class LandingPage(BasePage):
    """Drive and read every part of the portfolio page a test touches.

    Args:
        page (Page): The Playwright page bound to this Page Object.
        base_url (str): The absolute URL of the application under test.
    """

    def __init__(self, page: Page, base_url: str) -> None:
        super().__init__(page)
        self._base_url = base_url
        #: Auditor for the links this page publishes (moved here 2026-08-09),
        #: held as a collaborator per ``README.md`` section "Key Features".
        self.links = LinkAuditor(page, base_url)

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    @allure.step("Open the portfolio landing page")
    def navigate(self) -> "LandingPage":
        """Load the landing page and wait for client-side decoration to finish.

        Returns:
            LandingPage: This instance, so a caller can chain into an assertion.
        """
        self.open(self._base_url)
        self.wait_for_client_side_decoration()
        return self

    @allure.step("Open the portfolio landing page without awaiting decoration")
    def navigate_without_decoration(self) -> "LandingPage":
        """Load the landing page without waiting for the decoder to run.

        Used where scripting is disabled, so the placeholders survive because
        the decoder never executes.

        Returns:
            LandingPage: This instance, so a caller can chain into an assertion.
        """
        self.open(self._base_url)
        return self

    @allure.step("Wait for the anti-scraping decoder to replace every placeholder")
    def wait_for_client_side_decoration(self) -> None:
        """Wait until the page's ``DOMContentLoaded`` decoration has completed.

        Readiness is the ``span.enc-link`` placeholder count reaching zero, as
        an auto-retrying assertion, per ``README.md`` section "Test Design
        Principles".

        Returns:
            None
        """
        expect(self.link_placeholders()).to_have_count(0)

    def open_tab(self, tab: NavigationTab) -> None:
        """Click a navigation tab and wait for its panel to be revealed.

        Args:
            tab (NavigationTab): The tab to activate.

        Returns:
            None
        """
        # Decided 2026-07-28: the context-manager step, because Allure renders
        # decorator arguments as strings and cannot format "{tab.label}".
        with allure.step(f"Activate the '{tab.label}' tab"):
            self.nav_tab(tab).click()
            expect(self.tab_panel(tab)).to_be_visible()

    # ------------------------------------------------------------------
    # Locators
    # ------------------------------------------------------------------

    def open_project_from_evidence(
        self, tab: NavigationTab, *, key: str | None = None
    ) -> None:
        """Open a cited project through its Evidence cross-reference.

        Args:
            tab (NavigationTab): The project tab the control names.
            key (str | None): When given, the control is focused and this key
                pressed instead of a click. ``"Enter"`` and ``" "`` are the keys
                a button role must honor.

        Returns:
            None
        """
        how = "click" if key is None else f"{key} key"
        with allure.step(f"Open '{tab.label}' from its Evidence citation ({how})"):
            control = self.evidence_cross_reference_for(tab)
            if key is None:
                control.click()
            else:
                control.focus()
                control.press(key)

    def nav_bar(self) -> Locator:
        """Return the navigation landmark holding the tab strip.

        Returns:
            Locator: The page's ``<nav>`` element.
        """
        return self.page.get_by_role("navigation")

    def nav_tab(self, tab: NavigationTab) -> Locator:
        """Return one navigation tab, by role and a soft label match.

        Args:
            tab (NavigationTab): The tab to locate.

        Returns:
            Locator: The tab's list item, filtered on a soft match of its label.
        """
        return self.nav_tabs().filter(has_text=soft_text_pattern(tab.label))

    def nav_tabs(self) -> Locator:
        """Return every navigation tab at once.

        Returns:
            Locator: Every list item in the tab strip.
        """
        return self.nav_bar().get_by_role("listitem")

    def tab_panel(self, tab: NavigationTab) -> Locator:
        """Return the content panel a tab reveals.

        Args:
            tab (NavigationTab): The tab whose panel is wanted.

        Returns:
            Locator: The panel element, by its ``id``.
        """
        return self.page.locator(f"#{tab.panel_id}")

    def profile_header(self) -> Locator:
        """Return the persistent profile header above the tab strip.

        Returns:
            Locator: The ``#profile-header`` container.
        """
        return self.page.locator("#profile-header")

    def profile_photo(self) -> Locator:
        """Return the circular profile portrait.

        Returns:
            Locator: The portrait image, by role and a soft match of its
            accessible name.
        """
        return self.page.get_by_role("img", name=soft_text_pattern(PROFILE_NAME))

    def profile_photo_source(self) -> str:
        """Return the portrait's ``src`` exactly as authored in the markup.

        Returns:
            str: The raw attribute value, which may be a relative path, or an
            empty string when it is absent.
        """
        return self.profile_photo().get_attribute("src") or ""

    def profile_photo_is_first_party(self) -> bool:
        """Return whether the portrait is served by the site itself.

        Returns:
            bool: True when the source is a relative path or names the site's
            own host, False when it names another origin.
        """
        source = self.profile_photo_source()
        if not source.lower().startswith(("http://", "https://")):
            return True
        return urlparse(source).netloc.lower() == urlparse(self._base_url).netloc.lower()

    def profile_heading(self) -> Locator:
        """Return the heading carrying the site owner's name.

        Returns:
            Locator: The heading, by role rather than level, so promoting the
            ``<h2>`` to an ``<h1>`` does not break it.
        """
        return self.page.get_by_role("heading", name=soft_text_pattern(PROFILE_NAME))

    def site_footer(self) -> Locator:
        """Return the copyright footer.

        Returns:
            Locator: The ``#site-footer`` container or the ``contentinfo``
            landmark, so promoting the ``<div>`` to a ``<footer>`` does not
            break it.
        """
        return self.page.locator("#site-footer").or_(self.page.get_by_role("contentinfo"))

    def footer_owner_link(self) -> Locator:
        """Return the decoded owner link inside the copyright footer.

        Returns:
            Locator: The anchor the decoder writes in place of the footer's
            owner-name placeholder, by a soft match of its accessible name.
        """
        return self.site_footer().get_by_role("link", name=soft_text_pattern(PROFILE_NAME))

    def footer_owner_placeholder(self) -> Locator:
        """Return the footer's not-yet-decoded owner placeholder.

        Returns:
            Locator: The ``span.enc-link`` inside the footer, which survives only
            when scripting is unavailable.
        """
        return self.site_footer().locator("span.enc-link")

    def skills_matrix(self) -> Locator:
        """Return the technical skills table on the Home tab.

        Matched by its ``aria-label`` accessible name, with the
        ``table.skills-matrix`` class as a fallback.

        Returns:
            Locator: The skills matrix table.
        """
        home_panel = self.tab_panel(NavigationTab.HOME)
        return home_panel.get_by_role("table", name=SKILLS_MATRIX_LABEL).or_(
            home_panel.locator("table.skills-matrix")
        )

    def outcomes_table(self) -> Locator:
        """Return the engineering-outcomes table on its own tab.

        Returns:
            Locator: The outcomes table, by accessible name with the semantic
            class as a fallback.
        """
        panel = self.tab_panel(NavigationTab.ENGINEERING_OUTCOMES)
        return panel.get_by_role("table", name=OUTCOMES_TABLE_LABEL).or_(
            panel.locator("table.outcomes-table")
        )

    def outcome_rows(self) -> Locator:
        """Return every data row of the outcomes table.

        Returns:
            Locator: The ``tbody`` rows, one per published outcome, so a count
            reflects claims rather than markup.
        """
        return self.outcomes_table().locator("tbody tr")

    def evidence_cross_references(self) -> Locator:
        """Return every cross-reference control in the Evidence column.

        They are not anchors but elements with a button role, because they open
        another tab of this page and every anchor on the site must resolve to
        an absolute ``https`` or ``mailto`` target.

        Returns:
            Locator: The ``span.tab-jump`` controls.
        """
        return self.outcomes_table().locator("span.tab-jump")

    def citations_in_outcome_row(self, row_index: int) -> Locator:
        """Return the Evidence cross-references inside one outcome row.

        Args:
            row_index (int): The zero-based index of the row within ``tbody``.

        Returns:
            Locator: That row's cross-references, empty when it cites nothing.
        """
        return self.outcome_rows().nth(row_index).locator("span.tab-jump")

    def outcome_emphasis_displays(self, row_index: int) -> list[str]:
        """Return the computed ``display`` of each emphasis run in one outcome.

        The opening bold claim is promoted to its own line and mid-sentence
        emphasis is not; the difference is visible only as a computed style.

        Args:
            row_index (int): The zero-based index of the row within ``tbody``.

        Returns:
            list[str]: One computed ``display`` per ``<strong>``, in document
            order.
        """
        prose_cell = self.outcome_rows().nth(row_index).locator("td").first
        return list(
            prose_cell.locator("strong").evaluate_all(
                "nodes => nodes.map(node => getComputedStyle(node).display)"
            )
        )

    def evidence_cross_reference_for(self, tab: NavigationTab) -> Locator:
        """Return the first Evidence control that opens a given project tab.

        Args:
            tab (NavigationTab): The tab the control is expected to open.

        Returns:
            Locator: The first matching cross-reference.
        """
        return self.evidence_cross_references().filter(
            has_text=soft_text_pattern(tab.label)
        ).first

    def skills_matrix_rows(self) -> Locator:
        """Return the data rows of the skills matrix.

        Returns:
            Locator: The ``tbody`` rows, the reference for the shared row-hover
            treatment.
        """
        return self.skills_matrix().locator("tbody tr")

    def skills_matrix_header_row(self) -> Locator:
        """Return the header row of the skills matrix.

        Returns:
            Locator: The ``<thead>`` the mobile stylesheet hides.
        """
        return self.skills_matrix().locator("thead")

    def skills_matrix_column_header(self, header_name: str) -> Locator:
        """Return one column header of the skills matrix.

        Args:
            header_name (str): The header's accessible name, such as ``"Area"``.

        Returns:
            Locator: The matching header cell, by a soft match of its name.
        """
        return self.skills_matrix().get_by_role(
            "columnheader", name=soft_text_pattern(header_name)
        )

    def panel_heading(self, tab: NavigationTab) -> Locator:
        """Return the heading rendered at the top of a tab's panel.

        Args:
            tab (NavigationTab): The tab whose panel heading is wanted.

        Returns:
            Locator: The heading, as either role the site uses for a panel
            title: a ``heading`` on the Home panel or a spanning
            ``columnheader`` on the project tables.
        """
        panel = self.tab_panel(tab)
        heading_pattern = soft_text_pattern(tab.panel_heading)
        return panel.get_by_role("heading", name=heading_pattern).or_(
            panel.get_by_role("columnheader", name=heading_pattern)
        )

    def email_link(self) -> Locator:
        """Return the decoded contact link.

        Returns:
            Locator: The anchor the decoder writes in place of the
            ``#contact-email`` placeholder, by a soft match of its name.
        """
        return self.page.get_by_role("link", name=soft_text_pattern(EMAIL_LINK_LABEL))

    def noscript_fallback_link(self) -> Locator:
        """Return the LinkedIn fallback rendered when scripting is unavailable.

        Returns:
            Locator: The ``<noscript>`` contact link.
        """
        return self.profile_header().get_by_role("link", name=soft_text_pattern("LinkedIn"))

    def project_row(self, tab: NavigationTab, row_label: str) -> Locator:
        """Return one labeled row of a project table.

        The label must match the row's first cell alone and in full (since
        2026-11-10), never the row's position.

        Args:
            tab (NavigationTab): The project tab whose table is searched.
            row_label (str): The label in the row's first cell, such as
                ``"Repo"``.

        Returns:
            Locator: The matching ``<tr>``.
        """
        label_pattern = re.compile(
            rf"^\s*{soft_text_pattern(row_label).pattern}\s*$", re.IGNORECASE
        )
        return (
            self.tab_panel(tab)
            .locator("table.project-table > tbody > tr")
            .filter(has=self.page.locator("td:first-child", has_text=label_pattern))
        )

    def documentation_link(self, tab: NavigationTab) -> Locator:
        """Return the documentation links published by a project panel.

        The ``Documentation`` row holds one decoded anchor per repository the
        panel describes, each pointing at that repository's README.

        Args:
            tab (NavigationTab): The project tab whose links are wanted.

        Returns:
            Locator: The anchors inside the ``Documentation`` row.
        """
        return self.project_row(tab, DOCUMENTATION_ROW_LABEL).get_by_role("link")

    def repository_link(self, tab: NavigationTab) -> Locator:
        """Return the repository links published by a project panel.

        Args:
            tab (NavigationTab): The project tab whose links are wanted.

        Returns:
            Locator: The anchors inside the ``Repo`` row, one per repository
            the panel describes.
        """
        return self.project_row(tab, REPOSITORY_ROW_LABEL).get_by_role("link")

    def ci_status_badge(self, tab: NavigationTab) -> Locator:
        """Return the CI status badges published by a project panel.

        Args:
            tab (NavigationTab): The project tab whose badges are wanted.

        Returns:
            Locator: The badge images inside the CI status row: one for a panel
            describing one repository, one per gate for a chain of workflows.
        """
        return self.project_row(tab, CI_STATUS_ROW_LABEL).locator("img.ci-badge")

    def published_project_figures(self) -> list[tuple[str, str, int]]:
        """Return every figure a panel attributes to another repository's README.

        Each such figure is a ``span.qc-figure`` carrying the repository and the
        figure's name as data attributes. A span without both, or whose text is
        not a whole number, is skipped.

        Returns:
            list[tuple[str, str, int]]: One ``(repository, figure, value)``
            triple per marked figure, in document order, read from every panel
            whether or not it is shown.
        """
        return [
            (str(repository), str(figure), int(text.strip()))
            for repository, figure, text in self.page.eval_on_selector_all(
                "span.qc-figure",
                "nodes => nodes.map(node =>"
                " [node.dataset.repository, node.dataset.figure, node.textContent])",
            )
            if repository and figure and text.strip().isdigit()
        ]

    def panel_link(self, tab: NavigationTab) -> Locator:
        """Return the first decoded link inside a tab's panel.

        Args:
            tab (NavigationTab): The tab whose panel is searched.

        Returns:
            Locator: The panel's first anchor, the reference for the site's
            shared link styling.
        """
        return self.tab_panel(tab).get_by_role("link").first

    def hover_color(self, link: Locator) -> str:
        """Hover a link and return the color it resolves to.

        Args:
            link (Locator): A locator resolving to exactly one anchor.

        Returns:
            str: The computed ``color`` while the pointer rests on the link. The
            stylesheet declares no transition on it, so the value is settled
            when ``hover`` returns.
        """
        link.hover()
        return self.computed_color(link)

    def link_placeholders(self) -> Locator:
        """Return every not-yet-decoded obfuscated link placeholder.

        Returns:
            Locator: The ``span.enc-link`` elements. The class is the
            application's own decoding contract, so matching on it is exact.
        """
        return self.page.locator("span.enc-link")

    # ------------------------------------------------------------------
    # State queries
    # ------------------------------------------------------------------

    def contact_address(self) -> str:
        """Return the address the decoder wrote into the contact link.

        Returns:
            str: The bare address without its ``mailto:`` scheme, or an empty
            string when the link carries no ``href``.
        """
        href = self.email_link().get_attribute("href") or ""
        return href.removeprefix("mailto:")

    def body_text(self) -> str:
        """Return the rendered text of the document body.

        Returns:
            str: The visible text, which proves the raw contact address is never
            exposed in plain text.
        """
        return self.page.locator("body").inner_text()

    def navigation_row_count(self) -> int:
        """Return how many rows the tab strip wraps onto.

        Returns:
            int: ``1`` when every tab sits on one line, higher once the mobile
            stylesheet lets the flex container wrap.
        """
        navigation_tabs = self.nav_tabs()
        # Decided 2026-07-28: settle the layout before measuring, because a
        # bounding box is a point-in-time read Playwright does not retry.
        expect(navigation_tabs).to_have_count(len(NavigationTab))
        expect(navigation_tabs.first).to_be_visible()
        return self.distinct_row_count(navigation_tabs)

    # ------------------------------------------------------------------
    # Assertions over DOM internals
    # ------------------------------------------------------------------

    @allure.step("Verify the document title contains '{expected_fragment}'")
    def expect_title_contains(self, expected_fragment: str) -> None:
        """Assert that the document title contains the expected fragment.

        Args:
            expected_fragment (str): A substring the title must contain, in any
                case.

        Returns:
            None
        """
        expect(self.page).to_have_title(
            re.compile(re.escape(expected_fragment), re.IGNORECASE)
        )

    def expect_tab_selected(self, tab: NavigationTab) -> None:
        """Assert that a tab carries the router's ``active`` class.

        Args:
            tab (NavigationTab): The tab expected to be selected.

        Returns:
            None
        """
        with allure.step(f"Verify the '{tab.label}' tab is rendered as selected"):
            expect(self.nav_tab(tab)).to_have_class(ACTIVE_CLASS_PATTERN)

    def expect_tab_not_selected(self, tab: NavigationTab) -> None:
        """Assert that a tab does not carry the router's ``active`` class.

        Args:
            tab (NavigationTab): The tab expected to be unselected.

        Returns:
            None
        """
        with allure.step(f"Verify the '{tab.label}' tab is rendered as unselected"):
            expect(self.nav_tab(tab)).not_to_have_class(ACTIVE_CLASS_PATTERN)

    def expect_only_panel_visible(self, tab: NavigationTab) -> None:
        """Assert that one tab's panel is visible and every other panel hidden.

        Args:
            tab (NavigationTab): The single tab whose panel must be visible.

        Returns:
            None
        """
        with allure.step(f"Verify only the '{tab.label}' panel is displayed"):
            expect(self.tab_panel(tab)).to_be_visible()
            for other_tab in NavigationTab:
                if other_tab is not tab:
                    expect(self.tab_panel(other_tab)).to_be_hidden()

    @allure.step("Verify the contact link exposes a decoded mailto target")
    def expect_email_link_decoded(self) -> None:
        """Assert that the decoder produced a visible ``mailto:`` anchor.

        The anchor must read ``Email`` and carry a well-formed ``mailto:``
        target. Which mailbox it names is not asserted.

        Returns:
            None
        """
        contact_anchor = self.email_link()
        expect(contact_anchor).to_be_visible()
        expect(contact_anchor).to_have_text(soft_text_pattern(EMAIL_LINK_LABEL))
        expect(contact_anchor).to_have_attribute("href", MAILTO_PATTERN)

    @allure.step("Verify the copyright footer links the owner name to a decoded URL")
    def expect_footer_owner_link_decoded(self) -> None:
        """Assert that the footer's owner name is a decoded ``https`` anchor.

        The name is published through the same base64 ``enc-link`` mechanism as
        every other outbound link, so the decoded result is checked, not the
        encoded payload.

        Returns:
            None
        """
        owner_anchor = self.footer_owner_link()
        expect(owner_anchor).to_be_visible()
        expect(owner_anchor).to_have_text(soft_text_pattern(PROFILE_NAME))
        expect(owner_anchor).to_have_attribute("href", HTTPS_URL_PATTERN)
