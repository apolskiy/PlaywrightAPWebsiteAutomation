"""Coverage for the Engineering Outcomes tab and its cross-references.

The tab publishes one row per claimed outcome, each citing the project or
projects it can be verified against. Two properties matter here and neither is
covered by the navigation suite: every claim must carry at least one citation,
and following a citation must actually open the project it names.

The citations are deliberately not anchors. They navigate within this
single-page application, and :mod:`tests.test_link_obfuscation` requires every
anchor on the site to resolve to an absolute ``https``/``mailto`` target, so a
same-page fragment would violate that contract. They are published as elements
carrying a button role instead, which is why keyboard activation is asserted
separately - a pointer must not be the only way to reach a project.
"""

from __future__ import annotations

import allure
import pytest
from playwright.sync_api import expect

from pages.landing_page import LandingPage, NavigationTab

EPIC_NAME = "Portfolio Website Quality"
FEATURE_NAME = "Engineering Outcomes and Evidence"

#: The tabs an Evidence citation is allowed to open. Home and the outcomes tab
#: itself are excluded: a citation points at a project, never back at the index.
CITED_PROJECT_TABS: tuple[NavigationTab, ...] = (
    NavigationTab.REST_API,
    NavigationTab.PORTFOLIO_WEBSITE,
    NavigationTab.WEB_AUTOMATION,
    NavigationTab.HTTP_EMULATORS,
)


@allure.epic(EPIC_NAME)
@allure.feature(FEATURE_NAME)
@allure.story("The outcomes tab publishes its table of claims")
@allure.severity(allure.severity_level.CRITICAL)
def test_outcomes_tab_publishes_the_outcomes_table(desktop_page: LandingPage) -> None:
    """Opening the tab must reveal the outcomes table with at least one row.

    Args:
        desktop_page: Landing Page Object at the 1920x1080 viewport.
    """
    landing_page = desktop_page.navigate()

    with allure.step("Open the Engineering Outcomes tab"):
        landing_page.open_tab(NavigationTab.ENGINEERING_OUTCOMES)
        landing_page.expect_only_panel_visible(NavigationTab.ENGINEERING_OUTCOMES)

    with allure.step("Verify the outcomes table is rendered"):
        expect(landing_page.outcomes_table()).to_be_visible()

    with allure.step("Verify the table publishes at least one outcome"):
        row_count = landing_page.outcome_rows().count()
        assert row_count > 0, (
            "The Engineering Outcomes tab rendered its table but no rows. An "
            "empty evidence table is worse than no tab at all."
        )


@allure.epic(EPIC_NAME)
@allure.feature(FEATURE_NAME)
@allure.story("Every claimed outcome cites a project it can be verified against")
@allure.severity(allure.severity_level.CRITICAL)
def test_every_outcome_cites_at_least_one_project(desktop_page: LandingPage) -> None:
    """No outcome may stand without a citation.

    The tab's own premise is that each claim is verifiable in source rather than
    self-reported, so a row with an empty Evidence column silently breaks the
    promise the page makes to its reader.

    Args:
        desktop_page: Landing Page Object at the 1920x1080 viewport.
    """
    landing_page = desktop_page.navigate()
    landing_page.open_tab(NavigationTab.ENGINEERING_OUTCOMES)

    rows = landing_page.outcome_rows()

    with allure.step(f"Inspect the Evidence column of all {rows.count()} rows"):
        uncited = [
            row_index
            for row_index in range(rows.count())
            if landing_page.citations_in_outcome_row(row_index).count() == 0
        ]

    with allure.step("Verify every row carries at least one cross-reference"):
        assert not uncited, (
            "These outcome rows (zero-based) claim a result but cite no "
            f"project: {uncited}. Every claim needs a reachable source."
        )


@allure.epic(EPIC_NAME)
@allure.feature(FEATURE_NAME)
@allure.story("Following a citation opens the project tab it names")
@allure.severity(allure.severity_level.CRITICAL)
@pytest.mark.parametrize(
    "cited_tab", CITED_PROJECT_TABS, ids=lambda tab: tab.name.lower()
)
def test_evidence_cross_reference_opens_its_project_tab(
    desktop_page: LandingPage, cited_tab: NavigationTab
) -> None:
    """A citation must open the tab whose label it displays.

    This is the assertion that catches a mislabelled or stale ``data-target``:
    the control can look perfectly correct and still open the wrong project.

    Args:
        desktop_page: Landing Page Object at the 1920x1080 viewport.
        cited_tab: The project tab this citation is expected to open.
    """
    landing_page = desktop_page.navigate()
    landing_page.open_tab(NavigationTab.ENGINEERING_OUTCOMES)

    with allure.step(f"Follow the citation labelled '{cited_tab.label}'"):
        landing_page.open_project_from_evidence(cited_tab)

    with allure.step("Verify the cited project's panel is the only one shown"):
        landing_page.expect_only_panel_visible(cited_tab)

    with allure.step("Verify the navigation strip followed the jump"):
        landing_page.expect_tab_selected(cited_tab)
        landing_page.expect_tab_not_selected(NavigationTab.ENGINEERING_OUTCOMES)


@allure.epic(EPIC_NAME)
@allure.feature(FEATURE_NAME)
@allure.story("Emphasis inside an outcome does not fracture its sentence")
@allure.severity(allure.severity_level.NORMAL)
def test_only_the_leading_claim_is_promoted_to_its_own_line(
    desktop_page: LandingPage,
) -> None:
    """Only an outcome's opening claim may render as a block.

    Each row opens with a bold claim that the stylesheet lifts onto its own
    line, which is what makes the table scannable. Emphasis used later in the
    same sentence must stay inline: promoting it to a block splits the sentence
    around the emphasised words and leaves a stray fragment on the following
    line.

    This is a regression guard rather than a hypothetical. The rule was first
    written against every ``<strong>`` in the cell, which was harmless until a
    row emphasised a figure mid-prose, and the damage was visible only by
    looking at the rendered page.

    Args:
        desktop_page: Landing Page Object at the 1920x1080 viewport.
    """
    landing_page = desktop_page.navigate()
    landing_page.open_tab(NavigationTab.ENGINEERING_OUTCOMES)

    row_count = landing_page.outcome_rows().count()
    fractured: list[str] = []

    with allure.step(f"Inspect emphasis rendering across {row_count} outcomes"):
        for row_index in range(row_count):
            displays = landing_page.outcome_emphasis_displays(row_index)
            if not displays:
                continue
            if displays[0] != "block":
                fractured.append(
                    f"row {row_index}: leading claim renders as "
                    f"'{displays[0]}', so the row has no headline"
                )
            inline_offenders = [
                position
                for position, display in enumerate(displays[1:], start=1)
                if display == "block"
            ]
            if inline_offenders:
                fractured.append(
                    f"row {row_index}: mid-sentence emphasis at "
                    f"{inline_offenders} renders as a block, splitting the prose"
                )

    with allure.step("Verify no outcome has its sentence broken by emphasis"):
        assert not fractured, "Emphasis rendering is wrong:\n" + "\n".join(fractured)


@allure.epic(EPIC_NAME)
@allure.feature(FEATURE_NAME)
@allure.story("Outcome rows share the site's row-hover treatment")
@allure.severity(allure.severity_level.NORMAL)
def test_outcome_rows_share_the_table_hover_color(desktop_page: LandingPage) -> None:
    """An outcome row must tint on hover exactly like a skills-matrix row.

    The reference is another table rather than a hard coded color, so a future
    re-theme that changes the hover color everywhere stays green while a rule
    that drifts out of the shared selector list fails.

    Args:
        desktop_page: Landing Page Object at the 1920x1080 viewport.
    """
    landing_page = desktop_page.navigate()

    with allure.step("Capture the reference hover color from a skills-matrix row"):
        reference_hover = landing_page.hover_color(landing_page.skills_matrix_rows().first)

    landing_page.open_tab(NavigationTab.ENGINEERING_OUTCOMES)
    outcome_row = landing_page.outcome_rows().first

    with allure.step("Capture the outcome row's resting color"):
        resting_color = landing_page.computed_color(outcome_row)

    with allure.step("Verify the outcome row hovers to the shared color"):
        outcome_hover = landing_page.hover_color(outcome_row)
        assert outcome_hover == reference_hover, (
            "The outcomes table does not share the site's row-hover color: it "
            f"resolves to {outcome_hover} while a skills-matrix row resolves to "
            f"{reference_hover}. The outcomes selector is likely missing from "
            "the shared 'tbody tr:hover' rule."
        )

    with allure.step("Verify hovering actually changes the color"):
        assert outcome_hover != resting_color, (
            f"The outcome row renders {outcome_hover} whether hovered or not, "
            "so the row gives the reader no feedback."
        )


@allure.epic(EPIC_NAME)
@allure.feature(FEATURE_NAME)
@allure.story("Citations are operable from the keyboard")
@allure.severity(allure.severity_level.NORMAL)
def test_evidence_cross_reference_is_keyboard_operable(
    desktop_page: LandingPage,
) -> None:
    """A citation must activate on Enter, not only on click.

    The controls publish a button role. Anything that claims that role has to
    behave like one, or a keyboard-only visitor cannot reach the projects at
    all.

    Args:
        desktop_page: Landing Page Object at the 1920x1080 viewport.
    """
    landing_page = desktop_page.navigate()
    landing_page.open_tab(NavigationTab.ENGINEERING_OUTCOMES)

    with allure.step("Focus a citation and press Enter"):
        landing_page.open_project_from_evidence(
            NavigationTab.WEB_AUTOMATION, key="Enter"
        )

    with allure.step("Verify the cited project opened"):
        landing_page.expect_only_panel_visible(NavigationTab.WEB_AUTOMATION)
        landing_page.expect_tab_selected(NavigationTab.WEB_AUTOMATION)
