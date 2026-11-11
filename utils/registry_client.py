"""Reads a published Docker Hub image and reports the Python packages it installs.

Created: 2026-08-03
Last updated: 2026-11-10

This file contains ``fetch_pull_token`` and ``resolve_image_manifest``, which
obtain an anonymous pull token and resolve a tag to one platform's manifest;
``installed_distributions``, which reads every layer and returns each installed
distribution with its version; and ``application_distributions``, which
returns the same minus ``BASE_IMAGE_DISTRIBUTIONS``. Private helpers fetch,
decode and scan the layers.

``test_published_image_claims.py`` compares what this module reports for
``apolskiy/flask_app`` against the dependency closure the HTTP Emulators tab
claims. It runs in the weekly ``external`` check, since it reaches Docker Hub,
so a failure here reports an image that drifted from its claim and never
decides a deploy.

**The image is read from the registry, not run.** Pull token, manifest, then
layer blobs, reading the names of ``*.dist-info`` directories. No container
runtime and no HTTP client are involved.

**Both manifest spellings and both forms are accepted.** OCI and legacy Docker
media types, single manifest and multi-platform index: Buildx publishes an
index even for a one-platform image, so asking only for a manifest would 404 on
the tag it just pushed. From an index the linux/amd64 entry is followed, and
attestation entries, whose architecture is ``unknown``, are skipped.

**Layers are streamed, not decompressed whole.** A base-image layer expands to
several hundred megabytes and only its member names are needed.

Specified by ``README.md`` section "Key Features" (Published Artefact
Verification, Off the Deploy Path).
"""

from __future__ import annotations

import gzip
import io
import json
import tarfile
import urllib.request
from typing import Final

#: REGISTRY. The endpoint serving manifests and blobs of Docker Hub images.
REGISTRY_HOST: Final[str] = "https://registry-1.docker.io"

#: TOKEN ISSUER. The endpoint issuing the anonymous, pull-scoped bearer token.
TOKEN_HOST: Final[str] = "https://auth.docker.io/token"

#: ACCEPTED MEDIA TYPES when resolving a reference: OCI and legacy Docker,
#: single manifest and multi-platform index. Why both forms: the module
#: docstring.
MANIFEST_MEDIA_TYPES: Final[tuple[str, ...]] = (
    "application/vnd.oci.image.index.v1+json",
    "application/vnd.oci.image.manifest.v1+json",
    "application/vnd.docker.distribution.manifest.list.v2+json",
    "application/vnd.docker.distribution.manifest.v2+json",
)

#: SUBTRACTED, per ``README.md`` section "Key Features". The packaging tooling
#: every Python base image ships, which the application did not ask for.
BASE_IMAGE_DISTRIBUTIONS: Final[frozenset[str]] = frozenset({"pip", "setuptools", "wheel"})

#: TARGET PLATFORM selected from a multi-platform index.
TARGET_ARCHITECTURE: Final[str] = "amd64"
TARGET_OPERATING_SYSTEM: Final[str] = "linux"

#: BOUNDED. The ceiling of any one registry call, in seconds.
REQUEST_TIMEOUT_SECONDS: Final[int] = 30

#: METADATA MARKER. The suffix of an installed distribution's metadata directory.
DIST_INFO_SUFFIX: Final[str] = ".dist-info"


def _read_bytes(url: str, headers: dict[str, str]) -> bytes:
    """Return the raw body of one GET request.

    Args:
        url (str): The absolute URL to fetch.
        headers (dict): The request headers to send.

    Returns:
        bytes: The response body.

    Raises:
        urllib.error.URLError: When the request fails.
    """
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        return response.read()


def _read_json(url: str, headers: dict[str, str]) -> dict:
    """Return the body of one GET request, decoded as JSON.

    Args:
        url (str): The absolute URL to fetch.
        headers (dict): The request headers to send.

    Returns:
        dict: The decoded JSON document.
    """
    return json.loads(_read_bytes(url, headers).decode("utf-8"))


def fetch_pull_token(repository: str) -> str:
    """Return an anonymous pull token for a public repository.

    Args:
        repository (str): The repository, in ``namespace/name`` form.

    Returns:
        str: A bearer token the manifest and blob endpoints accept.
    """
    token_url = f"{TOKEN_HOST}?service=registry.docker.io&scope=repository:{repository}:pull"
    return _read_json(token_url, {})["token"]


def _manifest_headers(token: str) -> dict[str, str]:
    """Return the headers of a manifest request.

    Args:
        token (str): The bearer token from :func:`fetch_pull_token`.

    Returns:
        dict[str, str]: Headers carrying the token and every accepted manifest
        media type.
    """
    return {"Authorization": f"Bearer {token}", "Accept": ", ".join(MANIFEST_MEDIA_TYPES)}


def resolve_image_manifest(repository: str, reference: str, token: str) -> dict:
    """Return the single-platform image manifest a tag or digest resolves to.

    When the reference resolves to an index, its linux/amd64 entry is followed;
    attestation entries, whose architecture is ``unknown``, never match.

    Args:
        repository (str): The repository, in ``namespace/name`` form.
        reference (str): The tag name or digest to resolve.
        token (str): The bearer token from :func:`fetch_pull_token`.

    Returns:
        dict: The manifest document of the selected platform.

    Raises:
        LookupError: When the index carries no entry for the target platform.
    """
    manifest_url = f"{REGISTRY_HOST}/v2/{repository}/manifests/{reference}"
    manifest = _read_json(manifest_url, _manifest_headers(token))

    if "manifests" not in manifest:
        return manifest

    for entry in manifest["manifests"]:
        platform = entry.get("platform", {})
        if (
            platform.get("architecture") == TARGET_ARCHITECTURE
            and platform.get("os") == TARGET_OPERATING_SYSTEM
        ):
            return resolve_image_manifest(repository, entry["digest"], token)

    raise LookupError(
        f"{repository}:{reference} publishes no "
        f"{TARGET_OPERATING_SYSTEM}/{TARGET_ARCHITECTURE} image."
    )


def _parse_dist_info(member_path: str) -> tuple[str, str] | None:
    """Return the distribution name and version an archive member path names.

    Args:
        member_path (str): The path of one entry inside a layer archive, for
            example
            ``usr/local/lib/python3.14/site-packages/flask-3.1.2.dist-info/METADATA``.

    Returns:
        tuple[str, str] | None: A ``(name, version)`` pair, the name normalized
        to lower case with hyphens, or None when the path names no distribution.
    """
    for segment in member_path.split("/"):
        if not segment.endswith(DIST_INFO_SUFFIX):
            continue
        stem = segment[: -len(DIST_INFO_SUFFIX)]
        name, separator, version = stem.rpartition("-")
        if separator and name:
            return name.lower().replace("_", "-"), version
    return None


def _distributions_in_layer(blob: bytes) -> dict[str, str]:
    """Return the distributions whose metadata appears in one layer.

    The archive is streamed, reading member names only.

    Args:
        blob (bytes): The gzipped tar bytes of one image layer.

    Returns:
        dict[str, str]: Each distribution name found in the layer, mapped to
        its version.
    """
    found: dict[str, str] = {}
    decompressed = gzip.GzipFile(fileobj=io.BytesIO(blob))
    with tarfile.open(fileobj=decompressed, mode="r|") as archive:
        for member in archive:
            parsed = _parse_dist_info(member.name)
            if parsed is not None:
                found[parsed[0]] = parsed[1]
    return found


def installed_distributions(repository: str, reference: str = "latest") -> dict[str, str]:
    """Return every Python distribution installed in a published image.

    Args:
        repository (str): The repository, in ``namespace/name`` form.
        reference (str): The tag name or digest to inspect.

    Returns:
        dict[str, str]: Each distribution name mapped to its version, across
        every layer, base image tooling included.
    """
    token = fetch_pull_token(repository)
    manifest = resolve_image_manifest(repository, reference, token)
    blob_headers = {"Authorization": f"Bearer {token}"}

    found: dict[str, str] = {}
    for layer in manifest["layers"]:
        blob_url = f"{REGISTRY_HOST}/v2/{repository}/blobs/{layer['digest']}"
        found.update(_distributions_in_layer(_read_bytes(blob_url, blob_headers)))
    return found


def application_distributions(repository: str, reference: str = "latest") -> dict[str, str]:
    """Return the distributions an image installs beyond its base tooling.

    Args:
        repository (str): The repository, in ``namespace/name`` form.
        reference (str): The tag name or digest to inspect.

    Returns:
        dict[str, str]: Each distribution name mapped to its version, minus
        :data:`BASE_IMAGE_DISTRIBUTIONS`.
    """
    return {
        name: version
        for name, version in installed_distributions(repository, reference).items()
        if name not in BASE_IMAGE_DISTRIBUTIONS
    }
