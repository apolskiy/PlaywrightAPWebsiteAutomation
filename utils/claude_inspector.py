"""Asks Claude to triage a failed test and returns its report as text.

Created: 2026-07-28
Last updated: 2026-11-10

This file contains ``FailureContext``, the record of one failed test (its name,
page URL, error text, browser error log and DOM snapshot), and
``ClaudeTestInspector``, which sends that record to the Messages API and returns
the model's verdict, evidence, root cause and suggested fix. ``SYSTEM_PROMPT``
is the instruction the model receives, and two constants bound the call.

The failure hook in ``conftest.py`` calls the inspector after it has attached
the error log, screenshot and DOM, and attaches the returned report to Allure.
The inspector runs last and is advisory: a failure here produces no report and
never changes the test's outcome or hides the Playwright error.

**It never raises into the session.** Disabled diagnostics, a missing key or an
API error all return None, and the API error is logged as a warning.

**Both inputs are bounded and say so.** The log and the DOM are each cut to
their limit in ``config.settings``, and a cut input carries a note naming the
cut, so the model never reasons over a fragment believing it has the whole.

**The log comes before the DOM in the prompt.** It is far smaller, more likely
to name the cause outright, and the input that survives intact; the DOM is the
one cut when a page is large.

**The error log is a required field.** A caller with nothing to report passes
the report of a recorder that saw nothing, which states that no errors
occurred. That is a different claim from omitting the field, and the prompt
reasons from it.

**One call is held to 90 seconds**, so diagnostics never dominate the runtime
of the suite they report on, and its output to a short structured report.

Specified by ``README.md`` sections "Key Features" (AI-Powered Test
Diagnostics), "Configuration" and "Reporting".
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import anthropic

from config.settings import MAX_DIAGNOSTICS_CHARS, MAX_DOM_SNAPSHOT_CHARS, Settings

LOGGER = logging.getLogger(__name__)

#: BOUNDED. The wall-clock ceiling of one triage call, in seconds.
REQUEST_TIMEOUT_SECONDS: float = 90.0

#: BOUNDED. The output ceiling of one triage response, sized for a short
#: structured report.
MAX_RESPONSE_TOKENS: int = 8_000

SYSTEM_PROMPT: str = (
    "You are a senior test automation engineer triaging a failed Playwright "
    "end-to-end test against a static single-page portfolio website. You are "
    "given the assertion error, the browser's own error log for the page, and "
    "the fully rendered DOM captured at the moment of failure.\n\n"
    "How to read the error log:\n"
    "- It lists console errors, requests that failed outright, responses of 400 "
    "and above, and unhandled JavaScript exceptions, split into events the site "
    "under test is answerable for and events belonging to third-party hosts it "
    "merely embeds.\n"
    "- An unhandled exception is the strongest signal available: the site's only "
    "scripts are a tab router and a base64 link decoder, so an exception there "
    "explains a missing panel or an undecoded link directly, and the DOM only "
    "shows the aftermath.\n"
    "- A failure whose sole supporting evidence is third-party is "
    "'environment/flake'. The suite deliberately does not fail on third-party "
    "events, so if they are all you can find, say so.\n"
    "- An empty log is evidence too, not an absence of it: it rules out script "
    "exceptions and missing resources, which points at the DOM or at the "
    "assertion itself.\n\n"
    "Answer with these four sections and nothing else:\n"
    "1. VERDICT - one line: 'application regression', 'test defect', "
    "'environment/flake', or 'inconclusive'.\n"
    "2. EVIDENCE - the specific log entries, elements, attributes, or missing "
    "nodes that support the verdict. Quote real entries and real markup; never "
    "invent either. Say which input each piece came from.\n"
    "3. ROOT CAUSE - the most probable explanation in two sentences or fewer.\n"
    "4. SUGGESTED FIX - the concrete locator, assertion, or application change "
    "to make.\n\n"
    "If these inputs do not contain enough information to decide, say so in the "
    "VERDICT rather than guessing."
)


@dataclass(frozen=True)
class FailureContext:
    """Hold everything the inspector needs to triage one failed test.

    Attributes:
        test_name (str): The pytest node identifier of the failing test.
        page_url (str): The URL the browser was on when the test failed.
        error_text (str): The captured assertion or exception text.
        browser_diagnostics (str): The page's browser error log, as
            :meth:`~utils.page_diagnostics.PageDiagnostics.report` renders it.
            Required: a recorder that saw nothing still reports that no errors
            occurred.
        dom_snapshot (str): The fully rendered HTML of the page at failure time.
    """

    test_name: str
    page_url: str
    error_text: str
    browser_diagnostics: str
    dom_snapshot: str


class ClaudeTestInspector:
    """Triage failed tests with the Claude API and return a text report.

    Args:
        settings (Settings): The configuration supplying the credential, the
            model identifier and the enable flag.
        client (anthropic.Anthropic | None): A pre-built client to use. Left
            unset, a client is built on first use from the configured key.
    """

    def __init__(self, settings: Settings, client: anthropic.Anthropic | None = None) -> None:
        self._settings = settings
        self._client = client

    @property
    def enabled(self) -> bool:
        """Return whether triage calls are attempted at all.

        Returns:
            bool: True when diagnostics are switched on and a credential is
            present, False otherwise.
        """
        return self._settings.ai_diagnostics_enabled and self._settings.claude_api_key is not None

    @property
    def model(self) -> str:
        """Return the Claude model used for triage.

        Returns:
            str: The configured model identifier.
        """
        return self._settings.claude_model

    def analyze_failure(self, failure_context: FailureContext) -> str | None:
        """Return a root-cause report for one failed test.

        Args:
            failure_context (FailureContext): The failing test, its error text,
                its error log and the DOM captured at failure.

        Returns:
            str | None: The triage report as plain text, or None when
            diagnostics are disabled or unconfigured, or the API call failed.
            Callers read None as "no extra information".
        """
        if not self.enabled:
            return None

        try:
            response = self._request_analysis(failure_context)
        except anthropic.AnthropicError as api_error:
            # Decided 2026-07-28: diagnostics are advisory. Log and move on, so
            # the report still shows the real Playwright failure.
            LOGGER.warning(
                "Claude diagnostics unavailable for %s: %s",
                failure_context.test_name,
                api_error,
            )
            return None

        return self._extract_text(response)

    def _request_analysis(self, failure_context: FailureContext) -> anthropic.types.Message:
        """Return the Messages API response for one failure.

        Args:
            failure_context (FailureContext): The failure being triaged.

        Returns:
            anthropic.types.Message: The raw message the API returned.

        Raises:
            anthropic.AnthropicError: When the request cannot be completed. The
                caller downgrades it to a warning.
        """
        client = self._resolve_client()
        return client.with_options(timeout=REQUEST_TIMEOUT_SECONDS).messages.create(
            model=self._settings.claude_model,
            max_tokens=MAX_RESPONSE_TOKENS,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": self._build_prompt(failure_context)}],
        )

    def _resolve_client(self) -> anthropic.Anthropic:
        """Return the Anthropic client, building it on first use.

        Returns:
            anthropic.Anthropic: A memoized client bound to the configured key.
        """
        if self._client is None:
            self._client = anthropic.Anthropic(api_key=self._settings.claude_api_key)
        return self._client

    @staticmethod
    def _bounded(text: str, limit: int, label: str) -> str:
        """Return one prompt input capped at a limit, noting any cut in the text.

        Args:
            text (str): The input to bound.
            limit (int): The most characters to keep.
            label (str): The input's name, used in the truncation note.

        Returns:
            str: The text unchanged when within the limit, otherwise its first
            ``limit`` characters followed by a note saying it was truncated.
        """
        if len(text) <= limit:
            return text
        return f"{text[:limit]}\n[{label} truncated to the first {limit} characters]"

    @classmethod
    def _build_prompt(cls, failure_context: FailureContext) -> str:
        """Return the user turn describing one failure.

        Args:
            failure_context (FailureContext): The failure being triaged.

        Returns:
            str: The test name, page URL and error, then the bounded browser
            error log, then the bounded DOM snapshot, in that order.
        """
        return (
            f"FAILED TEST: {failure_context.test_name}\n"
            f"PAGE URL: {failure_context.page_url}\n\n"
            f"ASSERTION ERROR:\n{failure_context.error_text}\n\n"
            "BROWSER ERROR LOG:\n"
            f"{cls._bounded(failure_context.browser_diagnostics, MAX_DIAGNOSTICS_CHARS, 'Log')}"
            "\n\n"
            "RENDERED DOM AT FAILURE:\n"
            f"{cls._bounded(failure_context.dom_snapshot, MAX_DOM_SNAPSHOT_CHARS, 'DOM')}"
        )

    @staticmethod
    def _extract_text(response: anthropic.types.Message) -> str | None:
        """Return the text blocks of a Claude response joined into one string.

        Args:
            response (anthropic.types.Message): The message the API returned.

        Returns:
            str | None: The joined text, or None when the model produced no text,
            for example when the response stopped on a refusal.
        """
        text_blocks = [block.text for block in response.content if block.type == "text"]
        joined_text = "\n".join(text_blocks).strip()
        return joined_text or None
