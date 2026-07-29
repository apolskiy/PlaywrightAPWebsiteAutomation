"""Claude-powered failure triage for the Playwright suite.

When a web-first assertion fails, the raw Playwright error rarely explains *why*
the application changed - it only reports which locator stopped resolving. This
module hands the post-failure DOM snapshot to Claude and asks for a structured
root-cause hypothesis, which the pytest hook then attaches to the Allure report.

The inspector is strictly advisory: it never raises into the test session, and
any transport or credential problem degrades to "no report" rather than turning
a genuine product failure into an infrastructure failure.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import anthropic

from config.settings import MAX_DOM_SNAPSHOT_CHARS, Settings

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
    "given the assertion error and the fully rendered DOM captured at the "
    "moment of failure.\n\n"
    "Answer with these four sections and nothing else:\n"
    "1. VERDICT - one line: 'application regression', 'test defect', "
    "'environment/flake', or 'inconclusive'.\n"
    "2. EVIDENCE - the specific elements, attributes, or missing nodes in the "
    "DOM that support the verdict. Quote real snippets; never invent markup.\n"
    "3. ROOT CAUSE - the most probable explanation in two sentences or fewer.\n"
    "4. SUGGESTED FIX - the concrete locator, assertion, or application change "
    "to make.\n\n"
    "If the DOM does not contain enough information to decide, say so in the "
    "VERDICT rather than guessing."
)


@dataclass(frozen=True)
class FailureContext:
    """Everything the inspector needs to reason about a single failed test.

    Attributes:
        test_name: The pytest node identifier of the failing test.
        page_url: URL the browser was on when the failure occurred.
        error_text: The captured assertion or exception text.
        dom_snapshot: Fully rendered HTML of the page at failure time.
    """

    test_name: str
    page_url: str
    error_text: str
    dom_snapshot: str


class ClaudeTestInspector:
    """Analyses failed tests with the Claude API and returns a triage report.

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

    def analyse_failure(self, failure_context: FailureContext) -> str | None:
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
            A memoised client bound to the configured API key.
        """
        if self._client is None:
            self._client = anthropic.Anthropic(api_key=self._settings.claude_api_key)
        return self._client

    @staticmethod
    def _build_prompt(failure_context: FailureContext) -> str:
        """Render the user turn describing one failure.

        Args:
            failure_context: The failure being triaged.

        Returns:
            A prompt containing the test identity, the error, and a bounded DOM
            snapshot.
        """
        truncated_dom = failure_context.dom_snapshot[:MAX_DOM_SNAPSHOT_CHARS]
        truncation_note = (
            ""
            if len(failure_context.dom_snapshot) <= MAX_DOM_SNAPSHOT_CHARS
            else f"\n[DOM truncated to the first {MAX_DOM_SNAPSHOT_CHARS} characters]"
        )
        return (
            f"FAILED TEST: {failure_context.test_name}\n"
            f"PAGE URL: {failure_context.page_url}\n\n"
            f"ASSERTION ERROR:\n{failure_context.error_text}\n\n"
            f"RENDERED DOM AT FAILURE:\n{truncated_dom}{truncation_note}"
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
