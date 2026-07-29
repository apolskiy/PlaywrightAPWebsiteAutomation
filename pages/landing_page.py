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

import allure
from playwright.sync_api import Locator, Page, expect

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


class NavigationTab(Enum):
    """The five tabs published by the portfolio's vanilla-JS SPA router.

    Each member carries the tab's visible label, the ``id`` of the content panel
    the router reveals, and the heading rendered at the top of that panel. Home
    is the one tab whose panel heading differs from its label, because it hosts
    the skills matrix rather than a project table.
    """

    HOME = ("Home", "aphome1", "Technical Skills Matrix")
    REST_API = ("AI Assisted Rest API", "aprestapiclaude2", "AI Assisted Rest API")
    WEB_SITE = ("Web Site", "apwebsite3", "Web Site")
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

    def nav_bar(self) -> Locator:
        """Locate the navigation landmark holding the tab strip.

        Returns:
            A locator for the page's ``<nav>`` element.
        """
        return self.page.get_by_role("navigation")

    def nav_tab(self, tab: NavigationTab) -> Locator:
        """Locate a single navigation tab by its visible label.

        Args:
            tab: The tab to locate.

        Returns:
            A locator for the tab's list item.
        """
        return self.nav_bar().get_by_text(tab.label, exact=True)

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
            A locator for the portrait image, matched on its accessible name.
        """
        return self.page.get_by_role("img", name=PROFILE_NAME)

    def profile_heading(self) -> Locator:
        """Locate the profile name heading.

        Returns:
            A locator for the ``<h2>`` carrying the site owner's name.
        """
        return self.page.get_by_role("heading", name=PROFILE_NAME)

    def site_footer(self) -> Locator:
        """Locate the copyright footer.

        Returns:
            A locator for the footer container.
        """
        return self.page.locator("#site-footer")

    def footer_owner_link(self) -> Locator:
        """Locate the decoded owner link inside the copyright footer.

        Returns:
            A locator for the anchor the decoder substitutes for the footer's
            obfuscated owner-name placeholder.
        """
        return self.site_footer().get_by_role("link", name=PROFILE_NAME, exact=True)

    def footer_owner_placeholder(self) -> Locator:
        """Locate the footer's not-yet-decoded owner placeholder.

        Returns:
            A locator for the ``span.enc-link`` inside the footer, which only
            survives when scripting is unavailable.
        """
        return self.site_footer().locator("span.enc-link")

    def skills_matrix(self) -> Locator:
        """Locate the technical skills table on the Home tab.

        The table is addressed by its own semantic class rather than by ARIA
        role: the mobile stylesheet re-declares the row and cell ``display``
        values, which makes the computed table role browser-dependent below the
        breakpoint. The class name is part of the application's stylesheet
        contract and is stable across layouts.

        Returns:
            A locator for the skills matrix table.
        """
        return self.tab_panel(NavigationTab.HOME).locator("table.skills-matrix")

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
            A locator for the matching header cell.
        """
        return self.skills_matrix().get_by_role("columnheader", name=header_name)

    def panel_heading(self, tab: NavigationTab) -> Locator:
        """Locate the heading rendered at the top of a tab's content panel.

        Args:
            tab: The tab whose panel heading should be located.

        Returns:
            A locator for the heading, matched on its exact visible text.
        """
        return self.tab_panel(tab).get_by_text(tab.panel_heading, exact=True)

    def email_link(self) -> Locator:
        """Locate the decoded contact link.

        Returns:
            A locator for the anchor the decoder substitutes for the obfuscated
            ``#contact-email`` placeholder.
        """
        return self.page.get_by_role("link", name=EMAIL_LINK_LABEL, exact=True)

    def noscript_fallback_link(self) -> Locator:
        """Locate the LinkedIn fallback rendered when scripting is unavailable.

        Returns:
            A locator for the ``<noscript>`` contact link.
        """
        return self.profile_header().get_by_role("link", name="LinkedIn", exact=True)

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
        """Hover a link and read the colour it resolves to.

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
        expect(contact_anchor).to_have_text(EMAIL_LINK_LABEL)
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
        expect(owner_anchor).to_have_text(PROFILE_NAME)
        expect(owner_anchor).to_have_attribute("href", HTTPS_URL_PATTERN)
