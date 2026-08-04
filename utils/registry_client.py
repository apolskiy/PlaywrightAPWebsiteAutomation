"""Read-only Docker Hub registry client used to audit a published image.

The site's HTTP Emulators tab claims the published ``apolskiy/flask_app`` image
carries Flask and nothing beyond Flask's own dependency closure. That claim is
only ever as true as the last build behind it: a stray entry in the image's
``requirements.txt``, or a rebuild that picks up the development requirements,
would falsify it silently while the page keeps advertising the old number.

This module reads the published image straight from the registry - anonymous
pull token, manifest, then the layer blobs - and reports which Python
distributions the image actually installs. Nothing here runs Docker, because a
test that needed a container runtime could not run on the same hosted runner as
the rest of the suite.

Only the standard library is used. The suite already carries a browser engine
for its own transport; adding an HTTP client so that one test could inspect a
container would be a second way to make a request and a third thing to pin.
"""

from __future__ import annotations

import gzip
import io
import json
import tarfile
import urllib.request
from typing import Final

#: Registry endpoint serving manifests and blobs for Docker Hub images.
REGISTRY_HOST: Final[str] = "https://registry-1.docker.io"

#: Endpoint issuing the anonymous, pull-scoped bearer token the registry wants.
TOKEN_HOST: Final[str] = "https://auth.docker.io/token"

#: Media types accepted when resolving a reference. Both the OCI and the legacy
#: Docker spellings are listed, and both the single-manifest and the multi
#: platform index forms: Buildx publishes an index even for a one-platform
#: image, so asking only for a manifest would 404 on the tag it just pushed.
MANIFEST_MEDIA_TYPES: Final[tuple[str, ...]] = (
    "application/vnd.oci.image.index.v1+json",
    "application/vnd.oci.image.manifest.v1+json",
    "application/vnd.docker.distribution.manifest.list.v2+json",
    "application/vnd.docker.distribution.manifest.v2+json",
)

#: Packaging tooling every Python base image ships. It is not part of what the
#: application asked for, so callers comparing against a declared dependency set
#: subtract it rather than pretending the base image is empty.
BASE_IMAGE_DISTRIBUTIONS: Final[frozenset[str]] = frozenset({"pip", "setuptools", "wheel"})

#: Platform selected from a multi-platform index.
TARGET_ARCHITECTURE: Final[str] = "amd64"
TARGET_OPERATING_SYSTEM: Final[str] = "linux"

#: Ceiling on any single registry call, in seconds.
REQUEST_TIMEOUT_SECONDS: Final[int] = 30

#: Suffix marking an installed-distribution metadata directory.
DIST_INFO_SUFFIX: Final[str] = ".dist-info"


def _read_bytes(url: str, headers: dict[str, str]) -> bytes:
    """Perform one GET and return the raw response body.

    Args:
        url: Absolute URL to fetch.
        headers: Request headers to send.

    Returns:
        The response body as bytes.
    """
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        return response.read()


def _read_json(url: str, headers: dict[str, str]) -> dict:
    """Perform one GET and decode the response body as JSON.

    Args:
        url: Absolute URL to fetch.
        headers: Request headers to send.

    Returns:
        The decoded JSON document.
    """
    return json.loads(_read_bytes(url, headers).decode("utf-8"))


def fetch_pull_token(repository: str) -> str:
    """Obtain an anonymous pull token for a public repository.

    Args:
        repository: Repository in ``namespace/name`` form.

    Returns:
        A bearer token accepted by the manifest and blob endpoints.
    """
    token_url = f"{TOKEN_HOST}?service=registry.docker.io&scope=repository:{repository}:pull"
    return _read_json(token_url, {})["token"]


def _manifest_headers(token: str) -> dict[str, str]:
    """Build the headers used for a manifest request.

    Args:
        token: Bearer token from :func:`fetch_pull_token`.

    Returns:
        Headers carrying the token and every accepted manifest media type.
    """
    return {"Authorization": f"Bearer {token}", "Accept": ", ".join(MANIFEST_MEDIA_TYPES)}


def resolve_image_manifest(repository: str, reference: str, token: str) -> dict:
    """Resolve a tag or digest to a single-platform image manifest.

    A reference may resolve to an index listing several platforms, in which case
    the Linux/amd64 entry is followed. Attestation entries carry an ``unknown``
    architecture and are skipped rather than mistaken for an image.

    Args:
        repository: Repository in ``namespace/name`` form.
        reference: Tag name or digest to resolve.
        token: Bearer token from :func:`fetch_pull_token`.

    Returns:
        The manifest document for the selected platform.

    Raises:
        LookupError: If the index carries no entry for the target platform.
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
    """Extract a distribution name and version from an archive member path.

    Args:
        member_path: Path of one entry inside a layer archive, for example
            ``usr/local/lib/python3.14/site-packages/flask-3.1.2.dist-info/METADATA``.

    Returns:
        A ``(name, version)`` pair with the name normalised to lower case with
        hyphens, or ``None`` when the path names no distribution.
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
    """List the distributions whose metadata appears in one layer.

    The archive is streamed rather than decompressed whole: a base-image layer
    expands to several hundred megabytes and only its member names are needed.

    Args:
        blob: Gzipped tar bytes of a single image layer.

    Returns:
        Mapping of distribution name to version found in this layer.
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
    """Report every Python distribution installed in a published image.

    Args:
        repository: Repository in ``namespace/name`` form.
        reference: Tag name or digest to inspect.

    Returns:
        Mapping of distribution name to version, covering every layer. Base
        image tooling is included; callers subtract
        :data:`BASE_IMAGE_DISTRIBUTIONS` when they want only what the
        application installed.
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
    """Report the distributions an image installs beyond its base tooling.

    Args:
        repository: Repository in ``namespace/name`` form.
        reference: Tag name or digest to inspect.

    Returns:
        Mapping of distribution name to version, excluding the packaging tools
        every Python base image carries.
    """
    return {
        name: version
        for name, version in installed_distributions(repository, reference).items()
        if name not in BASE_IMAGE_DISTRIBUTIONS
    }
