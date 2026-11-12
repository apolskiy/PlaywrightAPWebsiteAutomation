"""Tests that every CI status badge the page publishes names a workflow that exists.

Created: 2026-11-12
Last updated: 2026-11-12

This file covers one behavior: every ``img.ci-badge`` source on the page,
across every panel, answers with something other than 404 or 410. It reads the
sources through ``LandingPage.published_badge_sources`` and resolves each
through ``LinkAuditor.url_status``.

The case is marked ``external`` and runs weekly, off the deployment path,
because it reaches github.com. A failure means a badge names a workflow file
that was renamed or deleted, so the panel shows a broken image where the build
status of that project should be.

**A badge is a claim about a workflow, and workflows get renamed.** GitHub
answers a badge request for a workflow file that no longer exists with 404.
Nothing else in the suite catches that: a badge links to the repository's
Actions page rather than to the workflow, so the link-rot check never fetches
the badge, and the panel tests read the ``src`` without resolving it, so that
GitHub's availability never decides a deploy. The Multi-LLM Evaluation tab
carries twelve badges for one repository whose workflows have already been
renamed once, which is what prompted this check.

Specified by ``README.md`` section "Coverage Summary".
"""

from __future__ import annotations

import allure
import pytest

from pages.landing_page import LandingPage

EPIC_NAME = "Portfolio Website Quality"
FEATURE_NAME = "Outbound Link Integrity"

#: GONE, decided 2026-11-12. The answers that mean a badge's workflow is gone,
#: matching the link-rot rule: 401, 403, 429 and no answer are not evidence of
#: it (README "Key Features", Outbound Link-Rot Detection).
GONE_STATUSES = (404, 410)


@pytest.mark.test_id("PAWA_10044")
@allure.epic(EPIC_NAME)
@allure.feature(FEATURE_NAME)
@allure.story("Every published CI badge names a workflow that still exists")
@allure.severity(allure.severity_level.NORMAL)
@pytest.mark.external
def test_published_badges_name_existing_workflows(desktop_page: LandingPage) -> None:
    """Assert the page publishes badges and none answers 404 or 410.

    Each distinct badge source is resolved once.

    Args:
        desktop_page (LandingPage): The landing Page Object at 1920x1080.

    Returns:
        None
    """
    landing_page = desktop_page.navigate()

    with allure.step("Read every CI badge source the page publishes"):
        sources = landing_page.published_badge_sources()

    with allure.step("Verify the page publishes at least one badge"):
        assert sources, (
            "The page publishes no CI badge, so there is nothing to verify. If the "
            "badges lost their ci-badge class, they are now unchecked."
        )

    with allure.step(f"Resolve {len(sources)} distinct badge sources"):
        statuses = {source: landing_page.links.url_status(source) for source in sources}
        allure.attach(
            "\n".join(f"{status}  {source}" for source, status in statuses.items()),
            name="Badge statuses",
            attachment_type=allure.attachment_type.TEXT,
        )

    with allure.step("Verify no badge names a workflow that is gone"):
        gone = {source: status for source, status in statuses.items() if status in GONE_STATUSES}
        assert not gone, (
            f"These badges name a workflow that no longer exists: {gone}. The "
            "workflow was renamed or deleted; point the badge at its current file."
        )
