"""Tests for the landing page's header, footer and tab routing.

Created: 2026-07-28
Last updated: 2026-11-10

This file contains the tests that the page loads with its title, profile
header and footer; that the portrait is self-hosted and decodes; that Home is
the default tab; that each tab reveals exactly its own panel, one case per
``NavigationTab``; that switching tabs deselects the previous one; that the
header and footer persist across every tab; and that Home renders the skills
matrix.

They run on the deployment path at the desktop viewport. A failure means the
page's identity or its single-page router is broken for every visitor, and
most other suites, which open tabs through the same router, are likely to fail
with it.

**No selectors here.** Every assertion goes through
:class:`~pages.landing_page.LandingPage`, and the module makes no direct
Playwright page call, so a markup change is absorbed by the Page Object alone.

**The title is checked for the owner's name, not a technology.** Until
2026-08-09 it required "Playwright", which tied the page's most visible SEO
element, the one a search result and a browser tab show, to one library in a
list that keeps changing. The person the portfolio belongs to is the part that
has to be there.

**The tab case grows with the enum.** Publishing a tab in ``NavigationTab``
adds a case with no edit here.

Specified by ``README.md`` sections "Project Architecture" and
"Test Design Principles".
"""

from __future__ import annotations

import allure
import pytest
from playwright.sync_api import expect

from pages.landing_page import PROFILE_NAME, LandingPage, NavigationTab

EPIC_NAME = "Portfolio Website Quality"
FEATURE_NAME = "Navigation and SPA Routing"


@pytest.mark.test_id("PAWA_10021")
@allure.epic(EPIC_NAME)
@allure.feature(FEATURE_NAME)
@allure.story("The landing page publishes the site owner's identity")
@allure.severity(allure.severity_level.BLOCKER)
def test_landing_page_exposes_owner_identity(desktop_page: LandingPage) -> None:
    """Assert the page loads with its owner's title, portrait, name and footer.

    Args:
        desktop_page (LandingPage): The landing Page Object at 1920x1080.

    Returns:
        None
    """
    landing_page = desktop_page.navigate()

    # Decided 2026-08-09: the title is checked for the owner's name, not a
    # technology. The module docstring holds the reason.
    with allure.step("Verify the document title identifies the site owner"):
        landing_page.expect_title_contains(PROFILE_NAME)

    with allure.step("Verify the permanent profile header is rendered"):
        expect(landing_page.profile_photo()).to_be_visible()
        expect(landing_page.profile_heading()).to_be_visible()

    with allure.step("Verify the copyright footer is rendered"):
        expect(landing_page.site_footer()).to_be_visible()


@pytest.mark.test_id("PAWA_10022")
@allure.epic(EPIC_NAME)
@allure.feature(FEATURE_NAME)
@allure.story("The profile portrait is a first-party asset that actually loads")
@allure.severity(allure.severity_level.CRITICAL)
def test_profile_photo_is_self_hosted_and_renders(desktop_page: LandingPage) -> None:
    """Assert the portrait is served by the site itself and decodes.

    Visibility alone proves nothing here: an ``<img>`` with alt text and fixed
    dimensions still takes up space when its source answers 404, so the case
    checks the intrinsic size the browser decoded.

    Args:
        desktop_page (LandingPage): The landing Page Object at 1920x1080.

    Returns:
        None
    """
    landing_page = desktop_page.navigate()

    with allure.step("Verify the portrait is not served by a third party"):
        assert landing_page.profile_photo_is_first_party(), (
            "The profile portrait is loaded from an external origin "
            f"({landing_page.profile_photo_source()}). Third-party image hosts "
            "expire or block traffic, which breaks the page for every visitor; "
            "serve the portrait from the site's own images/ directory."
        )

    with allure.step("Verify the portrait actually decoded"):
        natural_width, natural_height = landing_page.image_natural_size(
            landing_page.profile_photo()
        )
        assert natural_width > 0 and natural_height > 0, (
            "The profile portrait did not load: the browser decoded it to "
            f"{natural_width}x{natural_height}. The source "
            f"'{landing_page.profile_photo_source()}' is missing or unreadable."
        )


@pytest.mark.test_id("PAWA_10023")
@allure.epic(EPIC_NAME)
@allure.feature(FEATURE_NAME)
@allure.story("Home is the default tab on first load")
@allure.severity(allure.severity_level.CRITICAL)
def test_home_tab_is_selected_on_first_load(desktop_page: LandingPage) -> None:
    """Assert a cold load lands on Home with only the Home panel displayed.

    Args:
        desktop_page (LandingPage): The landing Page Object at 1920x1080.

    Returns:
        None
    """
    landing_page = desktop_page.navigate()

    with allure.step("Verify the Home tab carries the router's active state"):
        landing_page.expect_tab_selected(NavigationTab.HOME)

    with allure.step("Verify every other content panel stays collapsed"):
        landing_page.expect_only_panel_visible(NavigationTab.HOME)


@pytest.mark.test_id("PAWA_10024")
@allure.epic(EPIC_NAME)
@allure.feature(FEATURE_NAME)
@allure.story("Each tab reveals exactly one content panel")
@allure.severity(allure.severity_level.CRITICAL)
@pytest.mark.parametrize(
    "selected_tab", list(NavigationTab), ids=lambda tab: tab.name.lower()
)
def test_activating_a_tab_reveals_only_its_panel(
    desktop_page: LandingPage, selected_tab: NavigationTab
) -> None:
    """Assert activating a tab selects it, shows its panel and hides all others.

    Args:
        desktop_page (LandingPage): The landing Page Object at 1920x1080.
        selected_tab (NavigationTab): The tab this case activates.

    Returns:
        None
    """
    landing_page = desktop_page.navigate()

    landing_page.open_tab(selected_tab)

    with allure.step("Verify the clicked tab is marked as selected"):
        landing_page.expect_tab_selected(selected_tab)

    with allure.step("Verify panel visibility is mutually exclusive"):
        landing_page.expect_only_panel_visible(selected_tab)

    with allure.step("Verify the panel renders its own heading"):
        expect(landing_page.panel_heading(selected_tab)).to_be_visible()


@pytest.mark.test_id("PAWA_10025")
@allure.epic(EPIC_NAME)
@allure.feature(FEATURE_NAME)
@allure.story("Switching tabs clears the previously selected tab")
@allure.severity(allure.severity_level.NORMAL)
def test_switching_tabs_deselects_the_previous_tab(desktop_page: LandingPage) -> None:
    """Assert the router never leaves two tabs active at once.

    Args:
        desktop_page (LandingPage): The landing Page Object at 1920x1080.

    Returns:
        None
    """
    landing_page = desktop_page.navigate()

    with allure.step("Move away from the default Home tab"):
        landing_page.open_tab(NavigationTab.WEB_AUTOMATION)
        landing_page.expect_tab_selected(NavigationTab.WEB_AUTOMATION)
        landing_page.expect_tab_not_selected(NavigationTab.HOME)

    with allure.step("Return to Home and verify the state is handed back"):
        landing_page.open_tab(NavigationTab.HOME)
        landing_page.expect_tab_selected(NavigationTab.HOME)
        landing_page.expect_tab_not_selected(NavigationTab.WEB_AUTOMATION)


@pytest.mark.test_id("PAWA_10026")
@allure.epic(EPIC_NAME)
@allure.feature(FEATURE_NAME)
@allure.story("The profile header and footer persist across every tab")
@allure.severity(allure.severity_level.NORMAL)
def test_profile_header_and_footer_persist_across_tabs(desktop_page: LandingPage) -> None:
    """Assert the profile header, portrait and footer stay visible on every tab.

    Args:
        desktop_page (LandingPage): The landing Page Object at 1920x1080.

    Returns:
        None
    """
    landing_page = desktop_page.navigate()

    for navigation_tab in NavigationTab:
        with allure.step(f"Verify the shared chrome after opening '{navigation_tab.label}'"):
            landing_page.open_tab(navigation_tab)
            expect(landing_page.profile_header()).to_be_visible()
            expect(landing_page.profile_photo()).to_be_visible()
            expect(landing_page.site_footer()).to_be_visible()


@pytest.mark.test_id("PAWA_10027")
@allure.epic(EPIC_NAME)
@allure.feature(FEATURE_NAME)
@allure.story("The Home panel renders the technical skills matrix")
@allure.severity(allure.severity_level.NORMAL)
def test_home_panel_renders_the_skills_matrix(desktop_page: LandingPage) -> None:
    """Assert the Home tab shows the skills table with both column headers.

    Args:
        desktop_page (LandingPage): The landing Page Object at 1920x1080.

    Returns:
        None
    """
    landing_page = desktop_page.navigate()

    with allure.step("Verify the skills matrix is present on the default tab"):
        expect(landing_page.skills_matrix()).to_be_visible()

    with allure.step("Verify both column headers are labeled"):
        expect(landing_page.skills_matrix_column_header("Area")).to_be_visible()
        expect(
            landing_page.skills_matrix_column_header("Core Technologies & Methodologies")
        ).to_be_visible()
