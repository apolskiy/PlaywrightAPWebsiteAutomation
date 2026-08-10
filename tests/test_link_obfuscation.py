"""Coverage for the site's base64 anti-scraping link and e-mail obfuscation.

The application ships every outbound URL as a base64 payload inside a
``span.enc-link`` placeholder and decodes it on ``DOMContentLoaded``. These
tests verify both halves of that contract: the decoded state when scripting is
available, and the ``noscript`` fallback when it is not.
"""

from __future__ import annotations

import allure
import pytest
from playwright.sync_api import expect

from pages.landing_page import LandingPage

EPIC_NAME = "Portfolio Website Quality"
FEATURE_NAME = "Anti-Spam Link Obfuscation"

#: Schemes an outbound anchor is allowed to use once decoding has completed.
ALLOWED_LINK_SCHEMES = ("https://", "mailto:")

#: Suffixes that mark a scheme-less href as a link to another page of this site.
#: The site publishes every *outbound* target as a base64 payload, but it also
#: has genuine internal pages (the case study), and those are ordinary relative
#: links. Bare fragments stay disallowed: an in-page jump here is either a dead
#: link or a control that should not have been an anchor at all.
INTERNAL_PAGE_SUFFIXES = (".html", "/")


def is_safe_link_target(href: str) -> bool:
    """Decide whether an anchor's ``href`` is an acceptable target.

    Args:
        href: The raw ``href`` attribute value.

    Returns:
        True for an absolute ``https``/``mailto`` target or a relative link to
        another page of this site; False for a bare fragment, a relative path
        that is not a page, or any other scheme.
    """
    if href.startswith(ALLOWED_LINK_SCHEMES):
        return True
    if href.startswith(("#", "/", "javascript:", "data:", "http://")):
        return False
    return href.endswith(INTERNAL_PAGE_SUFFIXES)


@allure.epic(EPIC_NAME)
@allure.feature(FEATURE_NAME)
@allure.story("Every obfuscated placeholder is replaced by a real anchor")
@allure.severity(allure.severity_level.CRITICAL)
def test_all_placeholders_are_decoded_into_anchors(desktop_page: LandingPage) -> None:
    """No encoded placeholder may survive once the decoder has run.

    Args:
        desktop_page: Landing Page Object at the 1920x1080 viewport.
    """
    landing_page = desktop_page.navigate()

    with allure.step("Verify no encoded placeholder remains in the DOM"):
        expect(landing_page.link_placeholders()).to_have_count(0)

    with allure.step("Verify the decoder produced navigable anchors"):
        expect(landing_page.links.anchors().first).to_be_visible()


@allure.epic(EPIC_NAME)
@allure.feature(FEATURE_NAME)
@allure.story("Decoded links resolve to absolute, safe URL schemes")
@allure.severity(allure.severity_level.NORMAL)
def test_decoded_links_use_absolute_safe_schemes(desktop_page: LandingPage) -> None:
    """Decoding must yield absolute ``https``/``mailto`` targets, never fragments.

    Args:
        desktop_page: Landing Page Object at the 1920x1080 viewport.
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


@allure.epic(EPIC_NAME)
@allure.feature("Outbound Link Integrity")
@allure.story("Every published repository link still resolves")
@allure.severity(allure.severity_level.NORMAL)
@pytest.mark.external
def test_outbound_links_do_not_rot(desktop_page: LandingPage) -> None:
    """Each off-site target the page advertises must still exist.

    A portfolio's links decay silently: a repository is renamed or made private
    and the page keeps advertising it. This resolves every distinct outbound
    target and fails only on a definitive "gone" status, so a rate limit or a
    transient network fault cannot turn link-rot detection into a flaky test.

    Marked ``external``: it is the one test here that depends on third parties
    being reachable, so it is deselected on the deployment path and run on a
    schedule instead. Link rot happens over months; checking it on every push
    would put GitHub and Docker Hub in the critical path of a deploy signal and
    generate enough request pressure to trip rate limiting on its own.

    Args:
        desktop_page: Landing Page Object at the 1920x1080 viewport.
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
        # 404/410 are the only statuses that prove the resource is not there.
        # 401/403/429 mean "reachable but not to an anonymous, unthrottled
        # caller", and 0 means the request never completed - none of those is
        # evidence of rot, and failing on them would make this test a liability.
        rotted = {
            target: status for target, status in statuses.items() if status in (404, 410)
        }
        assert not rotted, (
            f"These published links no longer resolve: {rotted}. A portfolio "
            "that cites a missing repository is worse than one that cites none."
        )


@allure.epic(EPIC_NAME)
@allure.feature(FEATURE_NAME)
@allure.story("New-tab links are hardened against reverse tabnabbing")
@allure.severity(allure.severity_level.NORMAL)
def test_new_tab_links_declare_noopener_and_noreferrer(desktop_page: LandingPage) -> None:
    """Every ``target="_blank"`` anchor must carry ``noopener noreferrer``.

    Args:
        desktop_page: Landing Page Object at the 1920x1080 viewport.
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


@allure.epic(EPIC_NAME)
@allure.feature(FEATURE_NAME)
@allure.story("The contact address is decoded without ever being displayed")
@allure.severity(allure.severity_level.CRITICAL)
def test_contact_link_is_decoded_without_exposing_the_address(
    desktop_page: LandingPage,
) -> None:
    """The decoder must produce a working ``mailto:`` with no address in the text.

    What this guarantees is narrower than the test name suggests, and the limit
    is worth stating where the contract lives. The address is asserted to be
    absent from the *rendered text*, and simultaneously asserted to be present
    in the ``href`` - because a contact link that does not carry the address is
    not a contact link. So the browser will show it in the status bar on hover,
    and devtools will show it outright. That is inherent to a working anchor,
    not a gap in this check.

    The obfuscation defeats scrapers that read HTML without executing it. It
    does not defeat a headless browser, and base64 is an encoding rather than a
    cipher, so it does not defeat a scraper that decodes ``data-`` attributes
    either. The site's README states the same limit; this docstring exists so
    the boundary is legible to whoever next reads the assertion and wonders why
    the address is allowed to sit in the ``href``.

    Args:
        desktop_page: Landing Page Object at the 1920x1080 viewport.
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


@allure.epic(EPIC_NAME)
@allure.feature(FEATURE_NAME)
@allure.story("The copyright footer links the owner name to a decoded profile")
@allure.severity(allure.severity_level.NORMAL)
def test_copyright_footer_owner_name_is_a_decoded_link(desktop_page: LandingPage) -> None:
    """The footer's owner name must decode into a working outbound anchor.

    Args:
        desktop_page: Landing Page Object at the 1920x1080 viewport.
    """
    landing_page = desktop_page.navigate()

    with allure.step("Verify the owner name decoded into an https anchor"):
        landing_page.expect_footer_owner_link_decoded()

    with allure.step("Verify no encoded placeholder survives in the footer"):
        expect(landing_page.footer_owner_placeholder()).to_have_count(0)


@allure.epic(EPIC_NAME)
@allure.feature(FEATURE_NAME)
@allure.story("Without scripting the payloads stay encoded and a fallback shows")
@allure.severity(allure.severity_level.NORMAL)
def test_scriptless_visitors_see_the_noscript_fallback(scriptless_page: LandingPage) -> None:
    """With JavaScript disabled, no address is exposed and LinkedIn is offered.

    Args:
        scriptless_page: Landing Page Object whose context has scripting off.
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
