"""Page Object for the single-page portfolio at https://apolskiy.github.io/.

Locator policy
--------------
Accessible locators (``get_by_role``, ``get_by_text``) are used wherever the
markup exposes a role or an accessible name. The application ships no
``data-testid`` attributes, and its tab panels are plain ``<div>`` elements
carrying only an ``id``, so those panels are addressed by a flat ``#id``
selector. A single stable ``id`` is an intentional exception to the
"no raw CSS" rule; structural chains such as ``div > ul > li:nth-child(2)`` are
never used because they break on any markup reshuffle.

Assertion policy
----------------
Checks that depend on DOM internals invisible to a test author - the ``active``
class toggled by the SPA router, the ``mailto:`` payload produced by the
anti-scraping decoder - are published here as ``expect_*`` helpers built on
Playwright's auto-retrying assertions. Everything else is exposed as a
:class:`~playwright.sync_api.Locator` so tests can assert on it directly.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Final
from urllib.parse import urlparse

import allure
from playwright.sync_api import Error as PlaywrightError, Locator, Page, expect

from pages.base_page import BasePage

#: Matches the ``active`` token inside a space-separated ``class`` attribute
#: without matching substrings such as ``inactive``.
ACTIVE_CLASS_PATTERN: Final[re.Pattern[str]] = re.compile(r"(?:^|\s)active(?:\s|$)")

#: Shape of a decoded contact address, e.g. ``mailto:someone@example.com``.
MAILTO_PATTERN: Final[re.Pattern[str]] = re.compile(r"^mailto:[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")

#: Shape of a decoded outbound hyperlink.
HTTPS_URL_PATTERN: Final[re.Pattern[str]] = re.compile(r"^https://\S+$")

#: Label rendered in place of the decoded address, so scrapers never see it.
EMAIL_LINK_LABEL: Final[str] = "Email"

#: Accessible name of the profile portrait, taken from its ``alt`` attribute.
PROFILE_NAME: Final[str] = "Aleksandr Polskiy"

#: Accessible name of the skills table, published by the page as an
#: ``aria-label``. Tables are addressed by accessible name rather than by an
#: unqualified role so that adding a table to a panel cannot make an existing
#: locator ambiguous.
SKILLS_MATRIX_LABEL: Final[str] = "Technical Skills Matrix"

#: Accessible name of the engineering-outcomes table, published as an
#: ``aria-label``.
OUTCOMES_TABLE_LABEL: Final[str] = "Selected Engineering Outcomes"

#: Label of the project-table row that links a project's own documentation.
DOCUMENTATION_ROW_LABEL: Final[str] = "Documentation"


def soft_text_pattern(text: str) -> re.Pattern[str]:
    """Build a tolerant matcher for a piece of user-visible text.

    Locators built from this pattern survive the cosmetic edits that most often
    break a suite: a change of letter case (the stylesheet already upper-cases
    the tab labels through ``text-transform``), a change in surrounding
    whitespace or line wrapping, and extra words added around the label.

    The pattern stays anchored on word boundaries rather than matching a bare
    substring, so ``Web Site`` cannot silently match ``Web Automation`` and a
    genuine relabeling is still caught.

    Args:
        text: The expected visible text.

    Returns:
        A case-insensitive pattern in which each run of whitespace matches any
        whitespace, bounded by word boundaries.
    """
    spaced_words = r"\s+".join(re.escape(word) for word in text.split())
    return re.compile(rf"\b{spaced_words}\b", re.IGNORECASE)


class NavigationTab(Enum):
    """The six tabs published by the portfolio's vanilla-JS SPA router.

    Each member carries the tab's visible label, the ``id`` of the content panel
    the router reveals, and the heading rendered at the top of that panel. Home
    and Engineering Outcomes are the two tabs whose panel heading differs from
    the label, because they host a cross-project table rather than a single
    project's table.

    Declaration order matches the order the tabs appear in the navigation strip,
    so a parametrized test reads in the same order a visitor encounters them.
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

    @property
    def label(self) -> str:
        """Visible text of the tab.

        Returns:
            The tab label exactly as it appears in the DOM. The stylesheet
            upper-cases it for display only, which does not affect matching.
        """
        return self.value[0]

    @property
    def panel_id(self) -> str:
        """Identifier of the content panel controlled by this tab.

        Returns:
            The ``id`` attribute of the associated ``.tab-content`` element.
        """
        return self.value[1]

    @property
    def panel_heading(self) -> str:
        """Heading rendered at the top of this tab's content panel.

        Returns:
            The exact heading text used to prove the correct panel was revealed.
        """
        return self.value[2]


class LandingPage(BasePage):
    """Page Object encapsulating every interaction with the portfolio page.

    Args:
        page: The Playwright page bound to this Page Object.
        base_url: Absolute URL of the application under test.
    """

    def __init__(self, page: Page, base_url: str) -> None:
        super().__init__(page)
        self._base_url = base_url

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    @allure.step("Open the portfolio landing page")
    def navigate(self) -> "LandingPage":
        """Load the landing page and wait for client-side decoration to finish.

        Returns:
            This instance, so callers can chain straight into an assertion.
        """
        self.open(self._base_url)
        self.wait_for_client_side_decoration()
        return self

    @allure.step("Open the portfolio landing page without awaiting decoration")
    def navigate_without_decoration(self) -> "LandingPage":
        """Load the landing page without waiting for the decoder to run.

        Required by the scripting-disabled scenario, where the placeholders are
        expected to survive precisely because the decoder never executes.

        Returns:
            This instance, so callers can chain straight into an assertion.
        """
        self.open(self._base_url)
        return self

    @allure.step("Wait for the anti-scraping decoder to replace every placeholder")
    def wait_for_client_side_decoration(self) -> None:
        """Block until the page's ``DOMContentLoaded`` decoration has completed.

        The site rewrites every ``span.enc-link`` placeholder into a real anchor
        once its script runs. Waiting for that collection to drain is an exact,
        auto-retrying readiness signal - no fixed sleep and no network-idle
        heuristic is required.
        """
        expect(self.link_placeholders()).to_have_count(0)

    def open_tab(self, tab: NavigationTab) -> None:
        """Click a navigation tab and wait for its panel to be revealed.

        Args:
            tab: The tab to activate.
        """
        # Allure renders step arguments as strings before formatting the title,
        # so a "{tab.label}" placeholder cannot be used on the decorator form.
        # The context-manager form interpolates the label at call time instead.
        with allure.step(f"Activate the '{tab.label}' tab"):
            self.nav_tab(tab).click()
            expect(self.tab_panel(tab)).to_be_visible()

    # ------------------------------------------------------------------
    # Locators
    # ------------------------------------------------------------------

    def follow_evidence_cross_reference(self, tab: NavigationTab) -> None:
        """Click the Evidence control that opens a given project tab.

        Args:
            tab: The project tab the control names.

        Returns:
            None
        """
        with allure.step(f"Follow the Evidence cross-reference to '{tab.label}'"):
            self.evidence_cross_reference_for(tab).click()

    def activate_evidence_cross_reference_by_key(
        self, tab: NavigationTab, key: str = "Enter"
    ) -> None:
        """Focus an Evidence control and activate it from the keyboard.

        The controls carry a button role, so a pointer must not be the only way
        to operate them.

        Args:
            tab: The project tab the control names.
            key: The key to press once the control holds focus.

        Returns:
            None
        """
        with allure.step(f"Activate the '{tab.label}' cross-reference with {key}"):
            control = self.evidence_cross_reference_for(tab)
            control.focus()
            control.press(key)

    def nav_bar(self) -> Locator:
        """Locate the navigation landmark holding the tab strip.

        Returns:
            A locator for the page's ``<nav>`` element.
        """
        return self.page.get_by_role("navigation")

    def nav_tab(self, tab: NavigationTab) -> Locator:
        """Locate a single navigation tab by role and tolerant label match.

        Args:
            tab: The tab to locate.

        Returns:
            A locator for the tab's list item, selected by ARIA role and
            filtered on a soft label match so a case or spacing tweak in the
            markup does not break the locator.
        """
        return self.nav_tabs().filter(has_text=soft_text_pattern(tab.label))

    def nav_tabs(self) -> Locator:
        """Locate every navigation tab at once.

        Returns:
            A locator resolving to all five list items in the tab strip.
        """
        return self.nav_bar().get_by_role("listitem")

    def tab_panel(self, tab: NavigationTab) -> Locator:
        """Locate the content panel governed by a tab.

        Args:
            tab: The tab whose panel should be located.

        Returns:
            A locator for the panel element.
        """
        return self.page.locator(f"#{tab.panel_id}")

    def profile_header(self) -> Locator:
        """Locate the persistent profile header shown above the tab strip.

        Returns:
            A locator for the profile header container.
        """
        return self.page.locator("#profile-header")

    def profile_photo(self) -> Locator:
        """Locate the circular profile portrait.

        Returns:
            A locator for the portrait image, matched by role on a soft form of
            its accessible name.
        """
        return self.page.get_by_role("img", name=soft_text_pattern(PROFILE_NAME))

    def profile_photo_source(self) -> str:
        """Read the portrait's ``src`` exactly as authored in the markup.

        Returns:
            The raw attribute value, which may be a relative path.
        """
        return self.profile_photo().get_attribute("src") or ""

    def profile_photo_is_first_party(self) -> bool:
        """Whether the portrait is served by the site rather than a third party.

        A portrait hosted elsewhere is a availability risk the site does not
        control: a signed or expiring CDN URL eventually stops resolving, which
        breaks the page for every visitor.

        Returns:
            ``True`` when the source is a relative path or points at the site's
            own host; ``False`` when it points at an external origin.
        """
        source = self.profile_photo_source()
        if not source.lower().startswith(("http://", "https://")):
            return True
        return urlparse(source).netloc.lower() == urlparse(self._base_url).netloc.lower()

    def profile_heading(self) -> Locator:
        """Locate the profile name heading.

        Returns:
            A locator for the heading carrying the site owner's name, matched by
            role rather than by heading level, so promoting the ``<h2>`` to an
            ``<h1>`` does not break it.
        """
        return self.page.get_by_role("heading", name=soft_text_pattern(PROFILE_NAME))

    def site_footer(self) -> Locator:
        """Locate the copyright footer.

        Returns:
            A locator for the footer container. The ``id`` is tried alongside
            the ``contentinfo`` landmark, so the locator keeps working if the
            ``<div>`` is later promoted to a semantic ``<footer>``.
        """
        return self.page.locator("#site-footer").or_(self.page.get_by_role("contentinfo"))

    def footer_owner_link(self) -> Locator:
        """Locate the decoded owner link inside the copyright footer.

        Returns:
            A locator for the anchor the decoder substitutes for the footer's
            obfuscated owner-name placeholder, matched softly on its accessible
            name.
        """
        return self.site_footer().get_by_role("link", name=soft_text_pattern(PROFILE_NAME))

    def footer_owner_placeholder(self) -> Locator:
        """Locate the footer's not-yet-decoded owner placeholder.

        Returns:
            A locator for the ``span.enc-link`` inside the footer, which only
            survives when scripting is unavailable.
        """
        return self.site_footer().locator("span.enc-link")

    def skills_matrix(self) -> Locator:
        """Locate the technical skills table on the Home tab.

        The Home panel holds more than one table - the skills matrix and the
        engineering-outcomes table - so an unqualified table role is ambiguous
        and would fail strict-mode evaluation. The role is therefore matched by
        the table's accessible name, which the application publishes as an
        ``aria-label``.

        The semantic class is kept as a fallback for two reasons: the mobile
        stylesheet re-declares the row and cell ``display`` values, which makes
        the computed table role browser-dependent below the breakpoint; and the
        fallback keeps this locator working against a deployment that predates
        the ``aria-label``.

        Returns:
            A locator for the skills matrix table.
        """
        home_panel = self.tab_panel(NavigationTab.HOME)
        return home_panel.get_by_role("table", name=SKILLS_MATRIX_LABEL).or_(
            home_panel.locator("table.skills-matrix")
        )

    def outcomes_table(self) -> Locator:
        """Locate the engineering-outcomes table on its own tab.

        Returns:
            A locator for the outcomes table, matched by accessible name with
            the semantic class as a fallback.
        """
        panel = self.tab_panel(NavigationTab.ENGINEERING_OUTCOMES)
        return panel.get_by_role("table", name=OUTCOMES_TABLE_LABEL).or_(
            panel.locator("table.outcomes-table")
        )

    def outcome_rows(self) -> Locator:
        """Locate every data row of the outcomes table.

        Returns:
            A locator for the ``tbody`` rows, one per published outcome. The
            header row is excluded so a count reflects claims, not markup.
        """
        return self.outcomes_table().locator("tbody tr")

    def evidence_cross_references(self) -> Locator:
        """Locate every cross-reference control in the Evidence column.

        These are not anchors: they open another tab of this single-page
        application, and every anchor on the site is required to resolve to an
        absolute ``https``/``mailto`` target. They are published as elements
        with a button role instead.

        Returns:
            A locator for the ``span.tab-jump`` controls.
        """
        return self.outcomes_table().locator("span.tab-jump")

    def citations_in_outcome_row(self, row_index: int) -> Locator:
        """Locate the Evidence cross-references inside one outcome row.

        Args:
            row_index: Zero-based index of the row within ``tbody``.

        Returns:
            A locator for that row's cross-references, empty if the row cites
            nothing.
        """
        return self.outcome_rows().nth(row_index).locator("span.tab-jump")

    def evidence_cross_reference_for(self, tab: NavigationTab) -> Locator:
        """Locate the first Evidence control that opens a given project tab.

        Args:
            tab: The tab the control is expected to open.

        Returns:
            A locator for the first matching cross-reference.
        """
        return self.evidence_cross_references().filter(
            has_text=soft_text_pattern(tab.label)
        ).first

    def skills_matrix_rows(self) -> Locator:
        """Locate the data rows of the skills matrix.

        Returns:
            A locator for the ``tbody`` rows, used as the reference for the
            shared row-hover treatment.
        """
        return self.skills_matrix().locator("tbody tr")

    def skills_matrix_header_row(self) -> Locator:
        """Locate the header row of the skills matrix.

        Returns:
            A locator for the ``<thead>`` that the mobile stylesheet hides.
        """
        return self.skills_matrix().locator("thead")

    def skills_matrix_column_header(self, header_name: str) -> Locator:
        """Locate one column header of the skills matrix.

        Args:
            header_name: Accessible name of the column header, e.g. ``"Area"``.

        Returns:
            A locator for the matching header cell, matched softly on its
            accessible name.
        """
        return self.skills_matrix().get_by_role(
            "columnheader", name=soft_text_pattern(header_name)
        )

    def panel_heading(self, tab: NavigationTab) -> Locator:
        """Locate the heading rendered at the top of a tab's content panel.

        Args:
            tab: The tab whose panel heading should be located.

        Returns:
            A locator for the heading. Both roles the site uses for a panel
            title are accepted - a real ``heading`` on the Home panel and a
            spanning ``columnheader`` on the project tables - so one accessor
            serves every tab and survives a switch between the two.
        """
        panel = self.tab_panel(tab)
        heading_pattern = soft_text_pattern(tab.panel_heading)
        return panel.get_by_role("heading", name=heading_pattern).or_(
            panel.get_by_role("columnheader", name=heading_pattern)
        )

    def email_link(self) -> Locator:
        """Locate the decoded contact link.

        Returns:
            A locator for the anchor the decoder substitutes for the obfuscated
            ``#contact-email`` placeholder, matched softly on its accessible
            name.
        """
        return self.page.get_by_role("link", name=soft_text_pattern(EMAIL_LINK_LABEL))

    def noscript_fallback_link(self) -> Locator:
        """Locate the LinkedIn fallback rendered when scripting is unavailable.

        Returns:
            A locator for the ``<noscript>`` contact link.
        """
        return self.profile_header().get_by_role("link", name=soft_text_pattern("LinkedIn"))

    def documentation_link(self, tab: NavigationTab) -> Locator:
        """Locate the documentation link published by a project panel.

        Each project table carries a ``Documentation`` row whose cell holds a
        single decoded anchor pointing at that project's README. The row is
        matched by its label rather than by position, so re-ordering the table
        cannot silently retarget this locator.

        Args:
            tab: The project tab whose documentation link is wanted.

        Returns:
            A locator for the anchor inside the ``Documentation`` row.
        """
        documentation_row = (
            self.tab_panel(tab)
            .get_by_role("row")
            .filter(has_text=soft_text_pattern(DOCUMENTATION_ROW_LABEL))
        )
        return documentation_row.get_by_role("link")

    def panel_link(self, tab: NavigationTab) -> Locator:
        """Locate the first decoded link inside a tab's content panel.

        Args:
            tab: The tab whose panel should be searched.

        Returns:
            A locator for the panel's first anchor, used as the reference for
            the site's shared link styling.
        """
        return self.tab_panel(tab).get_by_role("link").first

    def hover_color(self, link: Locator) -> str:
        """Hover a link and read the color it resolves to.

        Args:
            link: A locator resolving to exactly one anchor.

        Returns:
            The computed ``color`` while the pointer rests on the link. The
            stylesheet declares no transition on this property, so the value is
            settled as soon as ``hover`` returns.
        """
        link.hover()
        return self.computed_color(link)

    def link_placeholders(self) -> Locator:
        """Locate every not-yet-decoded obfuscated link placeholder.

        Returns:
            A locator for the ``span.enc-link`` elements. The class name is the
            application's own decoding contract, so matching on it is exact
            rather than brittle.
        """
        return self.page.locator("span.enc-link")

    def content_links(self) -> Locator:
        """Locate every anchor in the document.

        Returns:
            A locator resolving to all links, decoded or otherwise.
        """
        return self.page.get_by_role("link")

    # ------------------------------------------------------------------
    # State queries
    # ------------------------------------------------------------------

    def decoded_link_hrefs(self) -> list[str]:
        """Collect the ``href`` of every anchor on the page.

        Returns:
            One entry per anchor, in document order. Anchors without an ``href``
            contribute an empty string so the caller can flag them.
        """
        anchors = self.content_links()
        return [
            anchors.nth(anchor_index).get_attribute("href") or ""
            for anchor_index in range(anchors.count())
        ]

    def outbound_link_targets(self) -> list[str]:
        """Collect the distinct off-site ``https`` targets published by the page.

        Returns:
            Unique absolute targets whose host differs from the application's
            own, in first-seen order. Internal page links and ``mailto:`` are
            excluded: neither can rot in a way an HTTP status would reveal.
        """
        own_host = urlparse(self._base_url).netloc
        seen: dict[str, None] = {}
        for href in self.decoded_link_hrefs():
            if not href.startswith("https://"):
                continue
            if urlparse(href).netloc == own_host:
                continue
            seen.setdefault(href, None)
        return list(seen)

    def url_status(self, url: str) -> int:
        """Resolve one URL and report the status it answers with.

        The request is issued through the browser's own request context rather
        than a separate HTTP client, so no additional dependency is introduced
        and the call inherits the browser's redirect handling.

        Args:
            url: An absolute URL.

        Returns:
            The final HTTP status code, or ``0`` when the request could not be
            completed at all - a caller cannot distinguish a dead link from a
            dead network without that difference.
        """
        try:
            return int(self.page.request.get(url, timeout=20_000).status)
        except PlaywrightError:
            return 0

    def new_tab_link_count(self) -> int:
        """Count anchors that the decoder marked as opening in a new tab.

        Returns:
            The number of anchors carrying ``target="_blank"``.
        """
        return self.page.locator('a[target="_blank"]').count()

    def unsafe_new_tab_link_count(self) -> int:
        """Count new-tab anchors missing the ``noopener noreferrer`` hardening.

        Returns:
            The number of ``target="_blank"`` anchors whose ``rel`` attribute
            omits either ``noopener`` or ``noreferrer``. A non-zero result is a
            reverse-tabnabbing exposure.
        """
        return self.page.locator(
            'a[target="_blank"]:not([rel~="noopener"]), '
            'a[target="_blank"]:not([rel~="noreferrer"])'
        ).count()

    def contact_address(self) -> str:
        """Read the address the decoder wrote into the contact link.

        Returns:
            The bare address without its ``mailto:`` scheme, or an empty string
            when the link carries no ``href``.
        """
        href = self.email_link().get_attribute("href") or ""
        return href.removeprefix("mailto:")

    def body_text(self) -> str:
        """Read the rendered text of the document body.

        Returns:
            The visible text content, used to prove that the raw contact address
            is never exposed in plain text.
        """
        return self.page.locator("body").inner_text()

    def navigation_row_count(self) -> int:
        """Determine how many rows the tab strip wraps onto.

        Returns:
            ``1`` when every tab sits on a single line, or a higher number once
            the mobile stylesheet allows the flex container to wrap.
        """
        navigation_tabs = self.nav_tabs()
        # Settle the layout before measuring: bounding boxes are a point-in-time
        # read and are not auto-retried by Playwright.
        expect(navigation_tabs).to_have_count(len(NavigationTab))
        expect(navigation_tabs.first).to_be_visible()
        return self.distinct_row_count(navigation_tabs)

    # ------------------------------------------------------------------
    # Assertions over DOM internals
    # ------------------------------------------------------------------

    @allure.step("Verify the document title contains '{expected_fragment}'")
    def expect_title_contains(self, expected_fragment: str) -> None:
        """Assert that the document title advertises the expected technology.

        Args:
            expected_fragment: Case-insensitive substring the title must contain.
        """
        expect(self.page).to_have_title(
            re.compile(re.escape(expected_fragment), re.IGNORECASE)
        )

    def expect_tab_selected(self, tab: NavigationTab) -> None:
        """Assert that a tab carries the router's ``active`` class.

        Args:
            tab: The tab expected to be selected.
        """
        with allure.step(f"Verify the '{tab.label}' tab is rendered as selected"):
            expect(self.nav_tab(tab)).to_have_class(ACTIVE_CLASS_PATTERN)

    def expect_tab_not_selected(self, tab: NavigationTab) -> None:
        """Assert that a tab does not carry the router's ``active`` class.

        Args:
            tab: The tab expected to be unselected.
        """
        with allure.step(f"Verify the '{tab.label}' tab is rendered as unselected"):
            expect(self.nav_tab(tab)).not_to_have_class(ACTIVE_CLASS_PATTERN)

    def expect_only_panel_visible(self, tab: NavigationTab) -> None:
        """Assert mutual exclusivity of the SPA content panels.

        Args:
            tab: The single tab whose panel must be visible.
        """
        with allure.step(f"Verify only the '{tab.label}' panel is displayed"):
            expect(self.tab_panel(tab)).to_be_visible()
            for other_tab in NavigationTab:
                if other_tab is not tab:
                    expect(self.tab_panel(other_tab)).to_be_hidden()

    @allure.step("Verify the contact link exposes a decoded mailto target")
    def expect_email_link_decoded(self) -> None:
        """Assert the anti-spam decoder produced a usable ``mailto:`` anchor.

        The address itself is intentionally not asserted: the test contract is
        that decoding happened and that the visible label still hides the
        address, not that any particular mailbox is configured.
        """
        contact_anchor = self.email_link()
        expect(contact_anchor).to_be_visible()
        expect(contact_anchor).to_have_text(soft_text_pattern(EMAIL_LINK_LABEL))
        expect(contact_anchor).to_have_attribute("href", MAILTO_PATTERN)

    @allure.step("Verify the copyright footer links the owner name to a decoded URL")
    def expect_footer_owner_link_decoded(self) -> None:
        """Assert the footer's owner name is a decoded outbound anchor.

        The name is published through the same base64 ``enc-link`` mechanism as
        every other outbound link, so the assertion checks the decoded result
        rather than the encoded payload.
        """
        owner_anchor = self.footer_owner_link()
        expect(owner_anchor).to_be_visible()
        expect(owner_anchor).to_have_text(soft_text_pattern(PROFILE_NAME))
        expect(owner_anchor).to_have_attribute("href", HTTPS_URL_PATTERN)
