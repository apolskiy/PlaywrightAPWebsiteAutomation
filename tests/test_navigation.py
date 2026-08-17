"""Header integrity and single-page-application routing coverage.

Every assertion here is expressed through :class:`~pages.landing_page.LandingPage`;
this module deliberately contains no selectors and no direct Playwright page
calls, so a markup change is absorbed by the Page Object alone.
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
    """The page must load with its title, portrait, name, and footer intact.

    Args:
        desktop_page: Landing Page Object at the 1920x1080 viewport.
    """
    landing_page = desktop_page.navigate()

    # The title is asserted on the owner's name rather than on a technology.
    # It previously required "Playwright", which tied the single most important
    # SEO element on the page to one library in a list that will keep changing -
    # and the title is what a search result and a browser tab actually show. The
    # person the portfolio belongs to is the part that has to be there.
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
    """The portrait must be served by the site and decode successfully.

    Being visible is not enough: an ``<img>`` with alt text and fixed dimensions
    still occupies space when its source 404s, so this checks the intrinsic size
    the browser actually decoded.

    Args:
        desktop_page: Landing Page Object at the 1920x1080 viewport.
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
    """A cold load must land on Home with only the Home panel displayed.

    Args:
        desktop_page: Landing Page Object at the 1920x1080 viewport.
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
    """Activating any tab must display its panel and hide all the others.

    Args:
        desktop_page: Landing Page Object at the 1920x1080 viewport.
        selected_tab: The navigation tab exercised by this parametrization.
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
    """The router must never leave two tabs in the active state at once.

    Args:
        desktop_page: Landing Page Object at the 1920x1080 viewport.
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
    """Chrome outside the tab container must survive every routing transition.

    Args:
        desktop_page: Landing Page Object at the 1920x1080 viewport.
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
    """The Home tab must present the skills table with both column headers.

    Args:
        desktop_page: Landing Page Object at the 1920x1080 viewport.
    """
    landing_page = desktop_page.navigate()

    with allure.step("Verify the skills matrix is present on the default tab"):
        expect(landing_page.skills_matrix()).to_be_visible()

    with allure.step("Verify both column headers are labeled"):
        expect(landing_page.skills_matrix_column_header("Area")).to_be_visible()
        expect(
            landing_page.skills_matrix_column_header("Core Technologies & Methodologies")
        ).to_be_visible()
