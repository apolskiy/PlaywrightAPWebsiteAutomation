"""Reads the figures another repository's README states about itself.

Created: 2026-11-10
Last updated: 2026-11-10

This file contains ``readme_url`` and ``fetch_readme``, which locate and
download a repository's README; ``stated_figure``, which finds the integer a
README states for one named figure; and ``FIGURE_PATTERNS``, the pattern that
finds each figure, keyed by repository and figure name.

``test_published_project_figures.py`` reads every figure the Multi-LLM
Evaluation tab marks up with its source, fetches that source's README through
this module and compares the two. It runs in the weekly ``external`` check,
since it reaches GitHub, so a failure here reports a quoted figure gone stale
and never decides a deploy.

**The source is the README's Status table**, where each project states its own
numbers, read from ``main``. Those numbers move whenever that project does, and
nothing on this site would otherwise notice.

**Each figure is found by a pattern written against the README's wording.**
That is deliberate, not fragile: a README that stops stating a figure in a
recognizable form leaves the site quoting a number its source no longer states,
and that fails rather than passing silently.

**Only the standard library is used**, reading ``raw.githubusercontent.com``
the same way the registry check reads its manifests, so no HTTP client is added.

Specified by ``README.md`` section "Coverage Summary".
"""

from __future__ import annotations

import re
import urllib.request
from typing import Final

#: OWNER of every repository whose figures the site quotes.
OWNER: Final[str] = "apolskiy"

#: SOURCE OF TRUTH. The branch whose README is read.
BRANCH: Final[str] = "main"

#: BOUNDED. The ceiling of one README fetch, in seconds.
REQUEST_TIMEOUT_SECONDS: Final[float] = 20.0

#: ONE PATTERN PER FIGURE, keyed by ``(repository, figure)``. Each captures
#: exactly one integer from that repository's README.
FIGURE_PATTERNS: Final[dict[tuple[str, str], re.Pattern[str]]] = {
    ("AP-Harness-QC", "suite-cases"): re.compile(r"\*\*(\d+) test cases, all passing\*\*"),
    ("AP-Harness-QC", "requirements"): re.compile(r"\|\s*Requirements traced\s*\|\s*(\d+)"),
    ("AP-Model-QC", "graded-cases"): re.compile(r"\*\*(\d+) written\*\*"),
    ("AP-Model-QC", "graded-evaluator"): re.compile(r"\*\*\d+ written\*\*: (\d+) evaluator"),
    ("AP-Model-QC", "graded-security"): re.compile(
        r"\*\*\d+ written\*\*: \d+ evaluator, (\d+) security"
    ),
    ("AP-Model-QC", "graded-tool"): re.compile(
        r"\*\*\d+ written\*\*: \d+ evaluator, \d+ security, (\d+) tool"
    ),
    ("AP-Model-QC", "corpora"): re.compile(r"\*\*(\d+) corpora, \d+ tasks\*\*"),
    ("AP-Model-QC", "tasks"): re.compile(r"\*\*\d+ corpora, (\d+) tasks\*\*"),
    ("AP-Model-QC", "preconditions"): re.compile(r"\|\s*Preconditions[^|]*\|\s*\*\*(\d+) cases"),
    ("AP-Model-QC", "requirements"): re.compile(r"rtm_model\.csv`\s*\|\s*(\d+) requirements"),
    ("AP-Model-QC", "candidate-responses"): re.compile(r"\*\*(\d+) candidate responses\*\*"),
    ("AP-Model-QC", "judgements"): re.compile(r"\*\*(\d+) judgements\*\*"),
}


def readme_url(repository: str) -> str:
    """Return the raw-content URL of a repository's README.

    Args:
        repository (str): The repository name under :data:`OWNER`, for example
            ``"AP-Model-QC"``.

    Returns:
        str: The absolute URL of the README on :data:`BRANCH`.
    """
    return f"https://raw.githubusercontent.com/{OWNER}/{repository}/{BRANCH}/README.md"


def fetch_readme(repository: str) -> str:
    """Return a repository's README, downloaded as text.

    Args:
        repository (str): The repository name under :data:`OWNER`.

    Returns:
        str: The README's Markdown source.

    Raises:
        urllib.error.URLError: When the README cannot be fetched.
    """
    request = urllib.request.Request(readme_url(repository))
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        return response.read().decode("utf-8")


def stated_figure(readme: str, repository: str, figure: str) -> int | None:
    """Return the value a README states for one figure.

    Args:
        readme (str): The README's Markdown source.
        repository (str): The repository the README belongs to.
        figure (str): The figure's name, as the site marks it up.

    Returns:
        int | None: The integer the README states, or None when it no longer
        states it in the form the pattern expects.

    Raises:
        KeyError: When no pattern is known for the figure, meaning the site
            marked up a figure nothing knows how to verify.
    """
    match = FIGURE_PATTERNS[(repository, figure)].search(readme)
    return int(match.group(1)) if match else None
