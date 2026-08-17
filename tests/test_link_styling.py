"""Coverage for the site's shared interactive link styling.

The stylesheet applies one hover color to links across the profile header, the
project tables, and the copyright footer. This module pins that consistency:
the footer link is asserted against a table link rather than against a hard
coded color, so a future re-theme that changes the hover color everywhere
stays green, while a rule that drifts out of the shared selector list fails.
"""

from __future__ import annotations

import allure
import pytest

from pages.landing_page import LandingPage, NavigationTab

EPIC_NAME = "Portfolio Website Quality"
FEATURE_NAME = "Interactive Link Styling"


@pytest.mark.test_id("PAWA_10020")
@allure.epic(EPIC_NAME)
@allure.feature(FEATURE_NAME)
@allure.story("The copyright link shares the hover color used in the tables")
@allure.severity(allure.severity_level.NORMAL)
def test_footer_owner_link_shares_the_table_hover_color(desktop_page: LandingPage) -> None:
    """Hovering the footer owner link must tint it like any in-table link.

    Args:
        desktop_page: Landing Page Object at the 1920x1080 viewport.
    """
    landing_page = desktop_page.navigate()
    footer_link = landing_page.footer_owner_link()

    with allure.step("Capture the footer link's resting color"):
        resting_color = landing_page.computed_color(footer_link)

    with allure.step("Capture the reference hover color from a project table link"):
        landing_page.open_tab(NavigationTab.REST_API)
        table_hover_color = landing_page.hover_color(
            landing_page.panel_link(NavigationTab.REST_API)
        )

    with allure.step("Verify the footer link hovers to the same color"):
        footer_hover_color = landing_page.hover_color(footer_link)
        assert footer_hover_color == table_hover_color, (
            "The copyright link does not share the site's hover color: it "
            f"resolves to {footer_hover_color} while a project-table link "
            f"resolves to {table_hover_color}. The footer selector is likely "
            "missing from the shared 'a:hover' rule."
        )

    with allure.step("Verify hovering actually changes the color"):
        assert footer_hover_color != resting_color, (
            f"The footer link renders {footer_hover_color} whether hovered or "
            "not, so the hover state gives the user no feedback."
        )
