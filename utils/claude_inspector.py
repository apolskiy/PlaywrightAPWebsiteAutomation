"""Claude-powered failure triage for the Playwright suite.

When a web-first assertion fails, the raw Playwright error rarely explains *why*
the application changed - it only reports which locator stopped resolving. This
module hands the post-failure DOM snapshot and the browser's own error log to
Claude and asks for a structured root-cause hypothesis, which the pytest hook
then attaches to the Allure report.

The two inputs answer different halves of the question. The DOM shows what the
page ended up as; the error log shows what went wrong on the way there, and it
frequently names the cause outright - a script that threw before it could bind
the tab router explains a missing panel far more directly than the absence of
that panel does. Sending only the DOM meant asking for a cause while withholding
the evidence for it.

The inspector is strictly advisory: it never raises into the test session, and
any transport or credential problem degrades to "no report" rather than turning
a genuine product failure into an infrastructure failure.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import anthropic

from config.settings import MAX_DIAGNOSTICS_CHARS, MAX_DOM_SNAPSHOT_CHARS, Settings

LOGGER = logging.getLogger(__name__)

#: Wall-clock ceiling for a single triage call, in seconds. Diagnostics must
#: never dominate the runtime of the suite they are reporting on.
REQUEST_TIMEOUT_SECONDS: float = 90.0

#: Output ceiling for one triage response. Sized for a short structured report
#: rather than a long-form essay.
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
    """Everything the inspector needs to reason about a single failed test.

    Attributes:
        test_name: The pytest node identifier of the failing test.
        page_url: URL the browser was on when the failure occurred.
        error_text: The captured assertion or exception text.
        browser_diagnostics: The rendered browser error log for the page, as
            produced by :meth:`~utils.page_diagnostics.PageDiagnostics.report`.
            Required rather than optional: a caller that has nothing to say here
            should pass the report of a recorder that saw nothing, which states
            that no errors occurred - a materially different claim from omitting
            the field, and one the triage prompt reasons from explicitly.
        dom_snapshot: Fully rendered HTML of the page at failure time.
    """

    test_name: str
    page_url: str
    error_text: str
    browser_diagnostics: str
    dom_snapshot: str


class ClaudeTestInspector:
    """Analyzes failed tests with the Claude API and returns a triage report.

    Args:
        settings: Resolved framework configuration supplying the credential,
            the model identifier, and the master enable flag.
        client: Optional pre-built Anthropic client. Injected by unit tests;
            production callers leave it unset so the client is created lazily
            from the configured API key.
    """

    def __init__(self, settings: Settings, client: anthropic.Anthropic | None = None) -> None:
        self._settings = settings
        self._client = client

    @property
    def enabled(self) -> bool:
        """Whether triage calls should be attempted at all.

        Returns:
            ``True`` when diagnostics are switched on and a credential is
            available; ``False`` otherwise.
        """
        return self._settings.ai_diagnostics_enabled and self._settings.claude_api_key is not None

    @property
    def model(self) -> str:
        """The Claude model used for triage.

        Returns:
            The configured model identifier.
        """
        return self._settings.claude_model

    def analyze_failure(self, failure_context: FailureContext) -> str | None:
        """Produce a root-cause report for one failed test.

        Args:
            failure_context: The failing test, its error text, and the DOM
                captured at the moment of failure.

        Returns:
            The triage report as plain text, or ``None`` when diagnostics are
            disabled, unconfigured, or the API call did not succeed. Callers
            treat ``None`` as "no extra information available".
        """
        if not self.enabled:
            return None

        try:
            response = self._request_analysis(failure_context)
        except anthropic.AnthropicError as api_error:
            # Diagnostics are advisory. Log and move on so the test report still
            # shows the real Playwright failure rather than an API problem.
            LOGGER.warning(
                "Claude diagnostics unavailable for %s: %s",
                failure_context.test_name,
                api_error,
            )
            return None

        return self._extract_text(response)

    def _request_analysis(self, failure_context: FailureContext) -> anthropic.types.Message:
        """Issue the Claude API call for a single failure.

        Args:
            failure_context: The failure being triaged.

        Returns:
            The raw message returned by the Messages API.

        Raises:
            anthropic.AnthropicError: If the request cannot be completed. The
                caller is responsible for downgrading this to a warning.
        """
        client = self._resolve_client()
        return client.with_options(timeout=REQUEST_TIMEOUT_SECONDS).messages.create(
            model=self._settings.claude_model,
            max_tokens=MAX_RESPONSE_TOKENS,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": self._build_prompt(failure_context)}],
        )

    def _resolve_client(self) -> anthropic.Anthropic:
        """Return the Anthropic client, constructing it on first use.

        Returns:
            A memoized client bound to the configured API key.
        """
        if self._client is None:
            self._client = anthropic.Anthropic(api_key=self._settings.claude_api_key)
        return self._client

    @staticmethod
    def _bounded(text: str, limit: int, label: str) -> str:
        """Cap one prompt input, saying so in the text when it was capped.

        A silent truncation is worse than a short input: the model would reason
        over a partial log or a partial document believing it had the whole one,
        and could then report with confidence that something is absent when it
        was merely cut off.

        Args:
            text: The input to bound.
            limit: Maximum number of characters to keep.
            label: Name of the input, used in the truncation note.

        Returns:
            The text, followed by an explicit note when it was shortened.
        """
        if len(text) <= limit:
            return text
        return f"{text[:limit]}\n[{label} truncated to the first {limit} characters]"

    @classmethod
    def _build_prompt(cls, failure_context: FailureContext) -> str:
        """Render the user turn describing one failure.

        The error log precedes the DOM. It is far smaller and far more likely to
        name the cause outright, and it is the input that survives intact - the
        DOM is the one that gets cut when a page is large.

        Args:
            failure_context: The failure being triaged.

        Returns:
            A prompt containing the test identity, the error, the bounded
            browser log, and the bounded DOM snapshot.
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
        """Concatenate the text blocks of a Claude response.

        Args:
            response: The message returned by the Messages API.

        Returns:
            The joined text content, or ``None`` when the model produced no text
            block - for example if the response stopped on a refusal.
        """
        text_blocks = [block.text for block in response.content if block.type == "text"]
        joined_text = "\n".join(text_blocks).strip()
        return joined_text or None
