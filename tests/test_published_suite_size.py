"""Coverage for the suite-size figures the site quotes to a reader.

The site states how many tests this suite runs, on the Web Automation tab and
again in the CI case study. Those numbers were maintained by hand, which is a
guarantee that they eventually stop being true: a test is added, the pipeline
still passes, and the page keeps advertising last month's figure with nothing
anywhere to notice.

The numbers stay written in the markup - a reader should see a number, not a
placeholder - but they are no longer trusted. Each figure is marked up so it can
be read back and compared against the suite that is running, so the claim fails
the build the moment it drifts instead of decaying quietly.

The counts come from collection rather than from the current selection, so
running a subset does not make the published figure look wrong. Two invocations
measure something other than the suite the site quotes - naming specific files,
and selecting more than one browser engine, since every browser-scoped test is
collected once per engine. Both skip rather than assert against a number that
was never describing that run.
"""

from __future__ import annotations

import allure
import pytest

from conftest import SuiteSize
from config.settings import Settings
from pages.landing_page import LandingPage
from pages.route_page import RoutePage

EPIC_NAME = "Portfolio Website Quality"
FEATURE_NAME = "Published Suite Size"

#: Route of the case study, which quotes the same figures as the landing page.
CASE_STUDY_ROUTE = "case-study.html"


def _assert_matches(published: dict[str, int], suite_size: SuiteSize, page_name: str) -> None:
    """Compare the figures a page publishes against the collected suite.

    Args:
        published: Scope-to-number mapping read from the page.
        suite_size: The suite size measured during collection.
        page_name: Human-readable page name used in failure messages.
    """
    with allure.step(f"Verify {page_name} publishes a suite size at all"):
        assert published, (
            f"{page_name} publishes no marked suite-size figure. The numbers are "
            "read back from the markup to keep them honest, so an unmarked figure "
            "is one nothing can verify."
        )

    with allure.step(f"Verify {page_name} quotes the collected total"):
        assert published.get("total") == suite_size.total, (
            f"{page_name} advertises {published.get('total')} tests but the suite "
            f"collects {suite_size.total}. Update the published figure, or the page "
            "is telling a reader something that is no longer true."
        )

    with allure.step(f"Verify {page_name} quotes the deployment-path count"):
        assert published.get("deploy") == suite_size.deployment, (
            f"{page_name} advertises {published.get('deploy')} tests on the "
            f"deployment path but {suite_size.deployment} are not marked external. "
            "Marking a test external changes what a deploy actually gates on."
        )


@pytest.mark.test_id("PAWA_10033")
@allure.epic(EPIC_NAME)
@allure.feature(FEATURE_NAME)
@allure.story("The landing page quotes the suite size it actually has")
@allure.severity(allure.severity_level.NORMAL)
def test_landing_page_publishes_the_actual_suite_size(
    desktop_page: LandingPage, suite_size: SuiteSize
) -> None:
    """The Web Automation tab must quote the collected suite size.

    Args:
        desktop_page: Landing Page Object at the 1920x1080 viewport.
        suite_size: Suite size measured during collection.
    """
    if suite_size.incomparable_reason is not None:
        pytest.skip(suite_size.incomparable_reason)

    landing_page = desktop_page.navigate()

    with allure.step("Read the suite-size figures published on the landing page"):
        published = landing_page.published_suite_counts()

    _assert_matches(published, suite_size, "The Web Automation tab")


@pytest.mark.test_id("PAWA_10034")
@allure.epic(EPIC_NAME)
@allure.feature(FEATURE_NAME)
@allure.story("The case study quotes the suite size it actually has")
@allure.severity(allure.severity_level.NORMAL)
def test_case_study_publishes_the_actual_suite_size(
    desktop_route_page: RoutePage,
    framework_settings: Settings,
    suite_size: SuiteSize,
) -> None:
    """The case study's cost table must quote the collected suite size.

    Args:
        desktop_route_page: Route Page Object at the 1920x1080 viewport.
        framework_settings: Resolved framework configuration.
        suite_size: Suite size measured during collection.
    """
    if suite_size.incomparable_reason is not None:
        pytest.skip(suite_size.incomparable_reason)

    with allure.step(f"Open /{CASE_STUDY_ROUTE}"):
        desktop_route_page.open(framework_settings.resolve_url(CASE_STUDY_ROUTE))

    with allure.step("Read the suite-size figures published in the case study"):
        published = desktop_route_page.published_suite_counts()

    _assert_matches(published, suite_size, "The CI case study")
