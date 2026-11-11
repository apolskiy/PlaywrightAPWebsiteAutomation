"""Tests for the site's base64 link and e-mail obfuscation.

Created: 2026-07-28
Last updated: 2026-11-10

This file contains the tests that every encoded placeholder is decoded into an
anchor; that decoded anchors use safe targets; that no outbound target has
rotted; that new-tab links carry ``noopener noreferrer``; that the contact
address is decoded into a ``mailto:`` without appearing as text; that the
footer owner name decodes into a link; and that a visitor without scripting
sees the ``noscript`` fallback. It also contains ``is_safe_link_target``, the
predicate the safe-target test applies to each ``href``.

All but the link-rot test run on the deployment path. A failure there means
the decoder did not run, produced an unsafe or unhardened link, or exposed the
address it exists to hide. The link-rot test is marked ``external`` and runs
weekly; its failure means a published target answers 404 or 410.

**Both halves of the contract are checked.** The site ships every outbound URL
as a base64 payload in a ``span.enc-link`` placeholder and decodes it on
``DOMContentLoaded``, so the suite checks the decoded state with scripting and
the ``noscript`` fallback without it.

**A safe target is absolute or another page of this site.** An ``https`` or
``mailto`` target passes, and so does a relative link ending in ``.html`` or
``/``, since the case study is a genuine internal page. A bare fragment fails:
an in-page jump here is a dead link or a control that should not be an anchor.

Specified by ``README.md`` sections "Key Features" (Outbound Link-Rot
Detection) and "Coverage Summary".
"""

from __future__ import annotations

import allure
import pytest
from playwright.sync_api import expect

from pages.landing_page import LandingPage

EPIC_NAME = "Portfolio Website Quality"
FEATURE_NAME = "Anti-Spam Link Obfuscation"

#: SAFE SCHEMES. The schemes a decoded anchor may use.
ALLOWED_LINK_SCHEMES = ("https://", "mailto:")

#: INTERNAL PAGES (added 2026-07-29). Suffixes that mark a scheme-less href as
#: a link to another page of this site, such as the case study. Bare fragments
#: stay disallowed; the module docstring holds the reason.
INTERNAL_PAGE_SUFFIXES = (".html", "/")


def is_safe_link_target(href: str) -> bool:
    """Return whether an anchor's ``href`` is an acceptable target.

    Args:
        href (str): The raw ``href`` attribute value.

    Returns:
        bool: True for an absolute ``https`` or ``mailto`` target or a relative
        link to another page of this site; False for a bare fragment, a
        root-relative path, a relative path that is not a page, or any other
        scheme.
    """
    if href.startswith(ALLOWED_LINK_SCHEMES):
        return True
    if href.startswith(("#", "/", "javascript:", "data:", "http://")):
        return False
    return href.endswith(INTERNAL_PAGE_SUFFIXES)


@pytest.mark.test_id("PAWA_10013")
@allure.epic(EPIC_NAME)
@allure.feature(FEATURE_NAME)
@allure.story("Every obfuscated placeholder is replaced by a real anchor")
@allure.severity(allure.severity_level.CRITICAL)
def test_all_placeholders_are_decoded_into_anchors(desktop_page: LandingPage) -> None:
    """Assert no encoded placeholder survives the decoder and anchors appear.

    Args:
        desktop_page (LandingPage): The landing Page Object at 1920x1080.

    Returns:
        None
    """
    landing_page = desktop_page.navigate()

    with allure.step("Verify no encoded placeholder remains in the DOM"):
        expect(landing_page.link_placeholders()).to_have_count(0)

    with allure.step("Verify the decoder produced navigable anchors"):
        expect(landing_page.links.anchors().first).to_be_visible()


@pytest.mark.test_id("PAWA_10014")
@allure.epic(EPIC_NAME)
@allure.feature(FEATURE_NAME)
@allure.story("Decoded links resolve to absolute, safe URL schemes")
@allure.severity(allure.severity_level.NORMAL)
def test_decoded_links_use_absolute_safe_schemes(desktop_page: LandingPage) -> None:
    """Assert every decoded anchor passes :func:`is_safe_link_target`.

    Args:
        desktop_page (LandingPage): The landing Page Object at 1920x1080.

    Returns:
        None
    """
    landing_page = desktop_page.navigate()

    decoded_hrefs = landing_page.links.published_hrefs()

    with allure.step(f"Inspect the {len(decoded_hrefs)} decoded anchors"):
        allure.attach(
            "\n".join(decoded_hrefs),
            name="Decoded link targets",
            attachment_type=allure.attachment_type.TEXT,
        )
        unsafe_hrefs = [href for href in decoded_hrefs if not is_safe_link_target(href)]
        assert not unsafe_hrefs, (
            "Every anchor must resolve to an absolute https/mailto target or to "
            f"another page of this site; found {unsafe_hrefs}."
        )


@pytest.mark.test_id("PAWA_10015")
@allure.epic(EPIC_NAME)
@allure.feature("Outbound Link Integrity")
@allure.story("Every published repository link still resolves")
@allure.severity(allure.severity_level.NORMAL)
@pytest.mark.external
def test_outbound_links_do_not_rot(desktop_page: LandingPage) -> None:
    """Assert the page advertises outbound targets and none answers 404 or 410.

    Each distinct off-site target is resolved once. Marked ``external``: it
    reaches third parties, so it runs weekly rather than on the deployment
    path. Design: ``README.md`` section "Key Features" (Outbound Link-Rot
    Detection).

    Args:
        desktop_page (LandingPage): The landing Page Object at 1920x1080.

    Returns:
        None
    """
    landing_page = desktop_page.navigate()

    targets = landing_page.links.outbound_targets()

    with allure.step(f"Resolve {len(targets)} distinct outbound targets"):
        statuses = {target: landing_page.links.url_status(target) for target in targets}
        allure.attach(
            "\n".join(f"{status}  {target}" for target, status in statuses.items()),
            name="Outbound link statuses",
            attachment_type=allure.attachment_type.TEXT,
        )

    with allure.step("Verify the page advertises at least one outbound target"):
        assert targets, (
            "No outbound links were found. Either the decoder did not run or "
            "the page stopped citing its own repositories."
        )

    with allure.step("Verify no target reports that it is gone"):
        # Decided 2026-07-29: only 404 and 410 count as rot. 401, 403, 429 and
        # 0 (no answer) are not evidence of it, per README "Key Features".
        rotted = {
            target: status for target, status in statuses.items() if status in (404, 410)
        }
        assert not rotted, (
            f"These published links no longer resolve: {rotted}. A portfolio "
            "that cites a missing repository is worse than one that cites none."
        )


@pytest.mark.test_id("PAWA_10016")
@allure.epic(EPIC_NAME)
@allure.feature(FEATURE_NAME)
@allure.story("New-tab links are hardened against reverse tabnabbing")
@allure.severity(allure.severity_level.NORMAL)
def test_new_tab_links_declare_noopener_and_noreferrer(desktop_page: LandingPage) -> None:
    """Assert new-tab anchors exist and every one carries ``noopener noreferrer``.

    Args:
        desktop_page (LandingPage): The landing Page Object at 1920x1080.

    Returns:
        None
    """
    landing_page = desktop_page.navigate()

    with allure.step("Verify the decoder opted some links into a new tab"):
        assert landing_page.links.new_tab_count() > 0, (
            "No anchor was decoded with target='_blank', so the data-nw opt-in "
            "is no longer being honoured."
        )

    with allure.step("Verify no new-tab link is missing its rel hardening"):
        assert landing_page.links.unhardened_new_tab_count() == 0, (
            "At least one target='_blank' anchor is missing rel='noopener "
            "noreferrer', which exposes the site to reverse tabnabbing."
        )


@pytest.mark.test_id("PAWA_10017")
@allure.epic(EPIC_NAME)
@allure.feature(FEATURE_NAME)
@allure.story("The contact address is decoded without ever being displayed")
@allure.severity(allure.severity_level.CRITICAL)
def test_contact_link_is_decoded_without_exposing_the_address(
    desktop_page: LandingPage,
) -> None:
    """Assert the contact anchor decodes to a ``mailto:`` absent from the text.

    The guarantee is narrower than the name suggests. The address must be
    absent from the rendered text and present in the ``href``, since a contact
    link without the address is not a contact link; the status bar on hover
    and devtools therefore show it, which is inherent to a working anchor.

    The obfuscation defeats scrapers that read HTML without executing it. It
    does not defeat a headless browser, and base64 is an encoding, not a
    cipher, so it does not defeat a scraper that decodes ``data-`` attributes
    either. The site's own README states the same limit; it is restated here
    so a reader of the assertion sees why the address may sit in the ``href``.

    Args:
        desktop_page (LandingPage): The landing Page Object at 1920x1080.

    Returns:
        None
    """
    landing_page = desktop_page.navigate()

    with allure.step("Verify the contact anchor carries a decoded mailto target"):
        landing_page.expect_email_link_decoded()

    with allure.step("Verify the address never appears in the rendered text"):
        contact_address = landing_page.contact_address()
        assert contact_address, "The contact anchor was decoded without an address."
        assert contact_address not in landing_page.body_text(), (
            "The decoded contact address is rendered as visible text, defeating "
            "the anti-scraping obfuscation."
        )


@pytest.mark.test_id("PAWA_10018")
@allure.epic(EPIC_NAME)
@allure.feature(FEATURE_NAME)
@allure.story("The copyright footer links the owner name to a decoded profile")
@allure.severity(allure.severity_level.NORMAL)
def test_copyright_footer_owner_name_is_a_decoded_link(desktop_page: LandingPage) -> None:
    """Assert the footer owner name decodes into an ``https`` anchor.

    Args:
        desktop_page (LandingPage): The landing Page Object at 1920x1080.

    Returns:
        None
    """
    landing_page = desktop_page.navigate()

    with allure.step("Verify the owner name decoded into an https anchor"):
        landing_page.expect_footer_owner_link_decoded()

    with allure.step("Verify no encoded placeholder survives in the footer"):
        expect(landing_page.footer_owner_placeholder()).to_have_count(0)


@pytest.mark.test_id("PAWA_10019")
@allure.epic(EPIC_NAME)
@allure.feature(FEATURE_NAME)
@allure.story("Without scripting the payloads stay encoded and a fallback shows")
@allure.severity(allure.severity_level.NORMAL)
def test_scriptless_visitors_see_the_noscript_fallback(scriptless_page: LandingPage) -> None:
    """Assert that without scripting, payloads stay encoded and LinkedIn is offered.

    Args:
        scriptless_page (LandingPage): The landing Page Object whose context
            has JavaScript disabled.

    Returns:
        None
    """
    landing_page = scriptless_page.navigate_without_decoration()

    with allure.step("Verify the encoded placeholders survive untouched"):
        assert landing_page.link_placeholders().count() > 0, (
            "The obfuscated placeholders were replaced even though scripting is "
            "disabled, so the payloads are no longer script-gated."
        )

    with allure.step("Verify no decoded contact anchor is present"):
        expect(landing_page.email_link()).to_have_count(0)

    with allure.step("Verify the noscript LinkedIn fallback is offered instead"):
        expect(landing_page.noscript_fallback_link()).to_be_visible()

    with allure.step("Verify the footer owner name degrades to plain text"):
        expect(landing_page.footer_owner_placeholder()).to_have_count(1)
        expect(landing_page.footer_owner_link()).to_have_count(0)
