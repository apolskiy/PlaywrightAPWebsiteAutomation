"""Reading the figures another repository's README states about itself.

The Multi-LLM Evaluation tab quotes test, requirement and recording counts that
belong to two other repositories. Those numbers change whenever that project
moves, and nothing on this site would notice: the tab keeps rendering, and the
figure keeps looking like a figure. So each one is marked up with its source,
and this module reads the source - the Status table at the top of that
repository's README, which is where the project states its own numbers - so a
test can compare the two.

Each figure is located by a pattern written against the README's own wording.
That is deliberate rather than fragile: if the README stops stating a figure in
a recognisable form, the site is quoting a number its source no longer states,
and that should fail rather than pass silently.

Raw README content is read from ``raw.githubusercontent.com`` with the standard
library, the same way the registry check reads its manifests, so no HTTP client
is added for it.
"""

from __future__ import annotations

import re
import urllib.request
from typing import Final

#: Account that owns every repository whose figures the site quotes.
OWNER: Final[str] = "apolskiy"

#: Branch whose README is the source of truth.
BRANCH: Final[str] = "main"

#: Ceiling on a single README fetch, in seconds.
REQUEST_TIMEOUT_SECONDS: Final[float] = 20.0

#: Where each marked figure is stated, keyed by ``(repository, figure)``. Each
#: pattern captures exactly one integer from the repository's README.
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
    """Build the raw-content URL of a repository's README.

    Args:
        repository: Repository name under :data:`OWNER`, e.g. ``"AP-Model-QC"``.

    Returns:
        The absolute URL of the README on :data:`BRANCH`.
    """
    return f"https://raw.githubusercontent.com/{OWNER}/{repository}/{BRANCH}/README.md"


def fetch_readme(repository: str) -> str:
    """Download a repository's README as text.

    Args:
        repository: Repository name under :data:`OWNER`.

    Returns:
        The README's Markdown source.
    """
    request = urllib.request.Request(readme_url(repository))
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        return response.read().decode("utf-8")


def stated_figure(readme: str, repository: str, figure: str) -> int | None:
    """Find the value a README states for one figure.

    Args:
        readme: The README's Markdown source.
        repository: Repository the README belongs to.
        figure: Name of the figure, as the site marks it up.

    Returns:
        The integer the README states, or ``None`` when the README no longer
        states it in the form the pattern expects.

    Raises:
        KeyError: When no pattern is known for the figure, which means the site
            marked up a figure nothing knows how to verify.
    """
    match = FIGURE_PATTERNS[(repository, figure)].search(readme)
    return int(match.group(1)) if match else None
