"""Build the extensions API content payloads for one release.

Reads the package's manifest.json (v1 spec, see manifest.schema.json),
plus the package README, resolves the download URL from the GitHub
release's .zip asset, and writes two API content files:

* ``payload-create.json`` for POST /extensions (includes the ``id`` the
  catalogue requires on create),
* ``payload-update.json`` for PUT /extensions/{id} (identical except the
  ``id``, which that endpoint rejects as an unknown field).

The new release entry is keyed by the plain version (``"0.8.9"``), not the
git tag (``"branding-v0.8.9"``): the catalogue sorts and compares releases
by semver tag on every read, and the extensions site derives the editable
version from it. The entry is prepended to the extension's already
published releases (fetched from the API when ``API_TOKEN`` is set) so the
catalogue keeps its changelog history; without a token only the new entry
is submitted.

The catalogue API speaks its own type vocabulary, so the manifest type is
translated here ("module" -> "mod"); unknown types fail loudly rather than
being passed through.

Usage: build_payload.py <extension_id> <version> <tag>
"""

import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request


MAX_CONTENT_BYTES = 256 * 1024

# Catalogue cap on releases per extension (ExtensionContentSchema); older
# entries past this are dropped from the submitted history.
MAX_RELEASES = 100

# Manifest (manifest.json v1) type -> catalogue API type.
TYPE_MAP = {"module": "mod"}


def fail(message: str) -> None:
    print(f"::error::{message}", flush=True)
    sys.exit(1)


def find_package_dir(ext_id: str) -> str:
    """Locate the package directory by manifest id (directory names are
    Ucfirst while ids - and therefore tags - are lowercase)."""
    matches = []
    for entry in sorted(os.listdir(".")):
        manifest = os.path.join(entry, "manifest.json")
        if not os.path.isdir(entry) or not os.path.isfile(manifest):
            continue
        try:
            meta = json.load(open(manifest))
        except ValueError:
            fail(f"{manifest} is not valid JSON")
        if isinstance(meta, dict) and meta.get("id") == ext_id:
            matches.append(entry)
    if not matches:
        fail(f"No package with manifest id '{ext_id}' found")
    if len(matches) > 1:
        fail(f"Multiple packages claim manifest id '{ext_id}': {', '.join(matches)}")
    return matches[0]


def min_core_version(constraint: object, manifest_path: str) -> str:
    """Reduce a `requires.fossbilling` constraint to the plain minimum
    version the catalogue release record expects. Only simple >= pins are
    accepted; anything fancier must be resolved by hand before releasing."""
    if not isinstance(constraint, str):
        fail(f"{manifest_path} requires.fossbilling must be a version constraint string")
    match = re.fullmatch(r">=\s*(\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?)", constraint.strip())
    if not match:
        fail(
            f"{manifest_path} requires.fossbilling must be a simple '>=X.Y.Z' constraint "
            f"to publish, got {constraint!r}"
        )
    return match.group(1)


def fetch_existing_releases(ext_id: str) -> list:
    """Fetch the extension's currently published releases for merge history.

    Returns [] for a new extension (API 404) or when no API token is
    configured (offline use). Any other failure is fatal: silently
    submitting without history would wipe the catalogue's changelog.
    Entries are reduced to the release fields the catalogue schema
    accepts, so a newer API response shape can never fail validation.
    """
    api_token = os.environ.get("API_TOKEN", "")
    api_base = os.environ.get("API_BASE_URL", "")
    if not api_token or not api_base:
        return []

    http_request = urllib.request.Request(
        f"{api_base.rstrip('/')}/extensions/{ext_id}",
        headers={"Authorization": f"Bearer {api_token}"},
    )
    try:
        with urllib.request.urlopen(http_request, timeout=30) as response:
            body = json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return []
        fail(f"Could not fetch existing releases for '{ext_id}': HTTP {exc.code}")
    except Exception as exc:
        fail(f"Could not fetch existing releases for '{ext_id}': {exc}")
    result = body.get("result") if isinstance(body, dict) else None
    releases = result.get("releases") if isinstance(result, dict) else None
    if not isinstance(releases, list):
        fail(f"Catalogue response for '{ext_id}' has no releases list")
    known = []
    for entry in releases:
        if not isinstance(entry, dict):
            fail(f"Catalogue response for '{ext_id}' has a malformed release entry")
        known.append(
            {
                key: entry[key]
                for key in (
                    "tag",
                    "date",
                    "download_url",
                    "changelog_url",
                    "min_fossbilling_version",
                )
                if key in entry
            }
        )
    return known


def merge_releases(new_release: dict, ext_id: str) -> list:
    """Prepend the new release to the published history.

    Same-tag re-runs replace in place so a retried publish is idempotent;
    the catalogue caps the list at its 100-release maximum, oldest dropped.
    A pre-fix entry keyed by git tag (`<id>-v<semver>`) counts as the same
    release as its version, so re-publishing that version replaces the twin
    instead of doubling it; other legacy entries are preserved as-is.
    Ordering beyond newest-first does not matter here: the API re-sorts by
    semver tag on every read.
    """
    merged = [new_release]
    merged.extend(
        entry
        for entry in fetch_existing_releases(ext_id)
        if canonical_tag(entry.get("tag"), ext_id) != new_release["tag"]
    )
    return merged[:MAX_RELEASES]


def canonical_tag(tag: object, ext_id: str) -> object:
    """Collapse the pre-fix `<ext-id>-v<semver>` tag shape to its version.

    Comparison-only: stored entries are never rewritten here.
    """
    if isinstance(tag, str) and tag.startswith(f"{ext_id}-v"):
        return tag[len(ext_id) + 2 :]
    return tag


def main() -> None:
    ext_id, version, tag = sys.argv[1], sys.argv[2], sys.argv[3]
    if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", ext_id) or len(ext_id) > 200:
        fail(f"Extension id {ext_id!r} is not a valid catalogue id (lowercase alphanumeric segments separated by hyphens)")
    ext_dir = find_package_dir(ext_id)
    manifest_path = os.path.join(ext_dir, "manifest.json")
    meta = json.load(open(manifest_path))

    for field in (
        "manifest_version",
        "type",
        "id",
        "name",
        "version",
        "description",
        "author",
        "license",
        "homepage_url",
        "requires",
    ):
        if field not in meta:
            fail(f"{manifest_path} is missing required field '{field}'")
    if meta["manifest_version"] != 1:
        fail(f"{manifest_path} uses unsupported manifest_version {meta['manifest_version']!r} (this script handles v1)")
    if not isinstance(meta.get("author"), dict) or not meta["author"].get("name"):
        fail(f"{manifest_path} author must be an object with a name")
    if not isinstance(meta.get("requires"), dict):
        fail(f"{manifest_path} requires must be an object")
    if not isinstance(meta["requires"].get("fossbilling"), str):
        fail(f"{manifest_path} requires.fossbilling must be a version constraint string")

    if meta["type"] not in TYPE_MAP:
        fail(f"{manifest_path} has unsupported type {meta['type']!r} for catalogue submission")
    if meta["version"] != version:
        fail(f"{manifest_path} version {meta['version']!r} does not match release tag version {version!r}")

    requires = meta["requires"]
    min_version = min_core_version(requires["fossbilling"], manifest_path)

    readme_path = os.path.join(ext_dir, "README.md")
    if os.path.isfile(readme_path):
        readme = open(readme_path).read()
        if not readme.strip():
            fail(f"{readme_path} is empty")
    else:
        readme = meta["description"]
    if not readme.strip():
        fail(f"{manifest_path} has an empty description and no README.md to fall back on")

    release = json.loads(
        subprocess.run(
            ["gh", "api", f"repos/{os.environ['GITHUB_REPOSITORY']}/releases/tags/{tag}"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    )
    published_at = release.get("published_at") or release.get("created_at")
    html_url = release.get("html_url")

    zips = [
        a["browser_download_url"]
        for a in release.get("assets", [])
        if a.get("name", "").endswith(".zip")
    ]
    if not zips:
        fail(
            f"Release {tag} has no .zip asset. Attach the distributable zip "
            "(archive root must be the package directory contents, with no "
            "wrapper folder) before publishing."
        )
    download_url = zips[0]

    # The catalogue keys releases by plain semver version, not by git tag:
    # sorting, latest-release resolution, and the directory's edit form
    # all compare `tag` with semver. The git tag stays reachable through
    # the changelog and download URLs.
    new_release: dict = {
        "tag": version,
        "date": published_at,
        "download_url": download_url,
        "min_fossbilling_version": min_version,
    }
    if html_url:
        new_release["changelog_url"] = html_url

    license_name = meta["license"]
    if not isinstance(license_name, str) or not license_name.strip():
        fail(f"{manifest_path} license must be a non-empty SPDX identifier")
    content: dict = {
        "type": TYPE_MAP[meta["type"]],
        "name": meta["name"],
        "description": meta["description"],
        "releases": merge_releases(new_release, ext_id),
        "website": meta["homepage_url"],
        "license": {"name": license_name, "spdx_id": license_name},
        "readme": readme,
        "source": {"type": "github", "repo": os.environ.get("GITHUB_REPOSITORY", "FOSSBilling/modules")},
        "version": version,
        "download_url": download_url,
    }
    icon_url = meta.get("icon_url", "")
    if isinstance(icon_url, str) and re.match(r"https?://", icon_url):
        content["icon_url"] = icon_url

    create_content = dict(content)
    create_content["id"] = ext_id

    size = len(json.dumps(create_content).encode())
    if size > MAX_CONTENT_BYTES:
        fail("Built payload exceeds the 256 KiB content limit")

    with open("payload-create.json", "w") as handle:
        json.dump(create_content, handle)
    with open("payload-update.json", "w") as handle:
        json.dump(content, handle)
    print(f"Built payloads for {ext_id} {version} ({size} bytes)")


main()
