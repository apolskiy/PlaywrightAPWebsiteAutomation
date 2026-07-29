"""Coverage for the site's base64 anti-scraping link and e-mail obfuscation.

The application ships every outbound URL as a base64 payload inside a
``span.enc-link`` placeholder and decodes it on ``DOMContentLoaded``. These
tests verify both halves of that contract: the decoded state when scripting is
available, and the ``noscript`` fallback when it is not.
"""

from __future__ import annotations

import allure
from playwright.sync_api import expect

from pages.landing_page import LandingPage

EPIC_NAME = "Portfolio Website Quality"
FEATURE_NAME = "Anti-Spam Link Obfuscation"

#: URL schemes an anchor is allowed to use once decoding has completed.
ALLOWED_LINK_SCHEMES = ("https://", "mailto:")


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
        expect(landing_page.content_links().first).to_be_visible()


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

    decoded_hrefs = landing_page.decoded_link_hrefs()

    with allure.step(f"Inspect the {len(decoded_hrefs)} decoded anchors"):
        allure.attach(
            "\n".join(decoded_hrefs),
            name="Decoded link targets",
            attachment_type=allure.attachment_type.TEXT,
        )
        unsafe_hrefs = [
            href for href in decoded_hrefs if not href.startswith(ALLOWED_LINK_SCHEMES)
        ]
        assert not unsafe_hrefs, (
            "Decoded anchors must resolve to an absolute https or mailto target; "
            f"found {unsafe_hrefs}."
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
        assert landing_page.new_tab_link_count() > 0, (
            "No anchor was decoded with target='_blank', so the data-nw opt-in "
            "is no longer being honoured."
        )

    with allure.step("Verify no new-tab link is missing its rel hardening"):
        assert landing_page.unsafe_new_tab_link_count() == 0, (
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
    """The decoder must produce a working ``mailto:`` while hiding the address.

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
