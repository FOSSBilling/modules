"""Build the extensions API content payloads for one release.

Reads the package's manifest.json (v1 spec, see manifest.schema.json),
plus the package README, resolves the download URL from the GitHub
release's .zip asset, and writes two API content files:

* ``payload-create.json`` for POST /extensions (includes the ``id`` the
  API requires on create),
* ``payload-update.json`` for PUT /extensions/{id} (identical except the
  ``id``, which that endpoint rejects as an unknown field).

The new release entry is keyed by the plain version (``"0.8.9"``), not the
git tag (``"branding-v0.8.9"``): the API sorts and compares releases
by semver tag on every read, and the extensions site derives the editable
version from it. The entry is prepended to the extension's already
published releases so the API keeps its changelog history. Publishing
requires ``API_TOKEN`` and ``API_BASE_URL``.

The source ZIP and manifest are built by the package API before submission;
release entries reference the returned immutable artifact and SHA-256.

Usage: build_payload.py <extension_id> <version> <tag>
"""

import json
import os
import re
from pathlib import Path
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid

from resolve_release import parse_release_tag


MAX_CONTENT_BYTES = 256 * 1024

# Extensions API cap on releases per extension (ExtensionContentSchema); older
# entries past this are dropped from the submitted history.
MAX_RELEASES = 100

MANIFEST_TYPES = {"module", "theme", "payment-gateway", "server-manager", "domain-registrar", "translation"}


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
            meta = json.loads(Path(manifest).read_text())
        except ValueError:
            fail(f"{manifest} is not valid JSON")
        if isinstance(meta, dict) and meta.get("id") == ext_id:
            matches.append(entry)
    if not matches:
        fail(f"No package with manifest id '{ext_id}' found")
    if len(matches) > 1:
        fail(f"Multiple packages claim manifest id '{ext_id}': {', '.join(matches)}")
    return matches[0]


def fetch_existing_releases(ext_id: str) -> list | None:
    """Read published releases; only a 404 means the extension is new."""
    api_token = os.environ.get("API_TOKEN", "")
    api_base = os.environ.get("API_BASE_URL", "")
    if not api_token or not api_base:
        fail("API_TOKEN and API_BASE_URL are required to publish releases")

    http_request = urllib.request.Request(
        f"{api_base.rstrip('/')}/extensions/{ext_id}",
        headers={"Authorization": f"Bearer {api_token}"},
    )
    try:
        with urllib.request.urlopen(http_request, timeout=30) as response:
            body = json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        fail(f"Could not fetch existing releases for '{ext_id}': HTTP {exc.code}")
    except Exception as exc:
        fail(f"Could not fetch existing releases for '{ext_id}': {exc}")
    result = body.get("result") if isinstance(body, dict) else None
    releases = result.get("releases") if isinstance(result, dict) else None
    if not isinstance(releases, list):
        fail(f"Extensions API response for '{ext_id}' has no releases list")
    if not all(isinstance(entry, dict) for entry in releases):
        fail(f"Extensions API response for '{ext_id}' has a malformed release entry")
    return releases


def merge_releases(new_release: dict, history: list) -> list:
    """Replace a same-version release and retain at most MAX_RELEASES entries."""
    merged = [new_release]
    merged.extend(
        entry
        for entry in history
        if entry.get("tag") != new_release["tag"]
    )
    if new_release.get("is_latest"):
        merged = [new_release, *({key: value for key, value in entry.items() if key != "is_latest"} for entry in merged[1:])]
    retained = merged[:MAX_RELEASES]
    selected = next((entry for entry in merged if entry.get("is_latest")), None)
    if selected is not None and selected not in retained:
        retained[-1] = selected
    return retained


def api_json(path: str, data: bytes | None = None, content_type: str | None = None, *, timeout: float = 60) -> dict:
    token = os.environ.get("API_TOKEN", "")
    base = os.environ.get("API_BASE_URL", "").rstrip("/")
    if not token or not base:
        fail("API_TOKEN and API_BASE_URL are required to build directory packages")
    headers = {"Authorization": f"Bearer {token}"}
    if content_type:
        headers["Content-Type"] = content_type
    request = urllib.request.Request(base + path, data=data, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read(MAX_CONTENT_BYTES + 1)
            if len(body) > MAX_CONTENT_BYTES:
                fail("Package API response exceeds its size limit")
            document = json.loads(body)
            result = document.get("result") if isinstance(document, dict) else None
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        fail(f"Package API request failed: {exc}")
    if not isinstance(result, dict):
        fail("Package API returned no artifact metadata")
    return result


def build_package(manifest: dict, source_url: str) -> dict:
    if not os.environ.get("API_TOKEN") or not os.environ.get("API_BASE_URL"):
        fail("API_TOKEN and API_BASE_URL are required to build directory packages")
    expected = f"https://github.com/{os.environ['GITHUB_REPOSITORY']}/releases/download/"
    if not source_url.startswith(expected):
        fail("Source ZIP must be a release asset in this GitHub repository")
    try:
        with urllib.request.urlopen(source_url, timeout=60) as response:
            source = response.read(5 * 1024 * 1024 + 1)
    except (urllib.error.URLError, TimeoutError) as exc:
        fail(f"Source ZIP download failed: {exc}")
    if len(source) > 5 * 1024 * 1024:
        fail("Source ZIP exceeds the 5 MiB package limit")
    boundary = "package-" + uuid.uuid4().hex
    data = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="manifest"\r\nContent-Type: application/json\r\n\r\n'.encode()
        + json.dumps(manifest, ensure_ascii=False).encode()
        + f'\r\n--{boundary}\r\nContent-Disposition: form-data; name="source"; filename="source.zip"\r\nContent-Type: application/zip\r\n\r\n'.encode()
        + source + f'\r\n--{boundary}--\r\n'.encode()
    )
    job = api_json("/packages", data, f"multipart/form-data; boundary={boundary}")
    try:
        job_id = str(uuid.UUID(job["id"]))
    except (KeyError, ValueError, TypeError, AttributeError):
        fail("Package API returned an invalid job ID")
    deadline = time.monotonic() + 180
    artifact = None
    while True:
        if job.get("id") != job_id or job.get("extension_id") != manifest["id"]:
            fail("Package processing job does not match the submitted extension")
        if job.get("status") == "ready":
            artifact = job.get("artifact")
            break
        if job.get("status") == "failed":
            error = job.get("error")
            message = error.get("message") if isinstance(error, dict) else None
            fail(f"Package preparation failed: {message or 'unknown error'}")
        if job.get("status") not in ("queued", "processing"):
            fail("Package API returned an invalid processing state")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(1, remaining))
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        job = api_json(f"/package-jobs/{job_id}", timeout=min(60, remaining))
    if not isinstance(artifact, dict):
        fail(f"Package job {job_id} is still processing; retry publishing to reuse it")
    try:
        artifact_id = str(uuid.UUID(artifact["id"]))
    except (KeyError, ValueError, TypeError, AttributeError):
        fail("Package API returned an invalid artifact ID")
    if artifact.get("manifest") != manifest or not isinstance(artifact.get("sha256"), str) or not re.fullmatch(r"[a-f0-9]{64}", artifact["sha256"]):
        fail("Package API artifact does not match the submitted manifest or checksum format")
    if artifact.get("download_url") != os.environ["API_BASE_URL"].rstrip("/") + f"/packages/{artifact_id}/download":
        fail("Package API returned an unexpected download URL")
    return artifact


def main() -> None:
    ext_id, version, tag = sys.argv[1], sys.argv[2], sys.argv[3]
    try:
        target = parse_release_tag(tag)
    except ValueError as exc:
        fail(str(exc))
    if target != (ext_id, version):
        fail("Extension id and version must match the release tag")
    ext_dir = find_package_dir(ext_id)
    manifest_path = os.path.join(ext_dir, "manifest.json")
    meta = json.loads(Path(manifest_path).read_text())

    if "icon_url" in meta:
        fail("Remove icon_url from manifest.json; use icon.svg, icon.png, icon.webp or icon.avif at the package root")
    icons = [Path(ext_dir) / name for name in ("icon.svg", "icon.png", "icon.webp", "icon.avif") if (Path(ext_dir) / name).exists()]
    if len(icons) > 1 or any(icon.is_symlink() or not icon.is_file() for icon in icons):
        fail("Include at most one regular package icon")

    for field in (
        "manifest_version",
        "type",
        "id",
        "name",
        "version",
        "description",
        "author",
        "license",
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

    if meta["type"] not in MANIFEST_TYPES:
        fail(f"{manifest_path} has unsupported type {meta['type']!r} for extension submission")
    if meta["version"] != version:
        fail(f"{manifest_path} version {meta['version']!r} does not match release tag version {version!r}")

    requires = meta["requires"]
    if not isinstance(requires.get("php"), str) or not requires["php"].strip():
        fail(f"{manifest_path} requires.php must be a non-empty version constraint string")

    license_name = meta["license"]
    if not isinstance(license_name, str) or not license_name.strip():
        fail(f"{manifest_path} license must be a non-empty license expression")

    readme_path = os.path.join(ext_dir, "README.md")
    if os.path.isfile(readme_path):
        readme = Path(readme_path).read_text()
        if not readme.strip():
            fail(f"{readme_path} is empty")
    else:
        readme = meta["description"]
    if not readme.strip():
        fail(f"{manifest_path} has an empty description and no README.md to fall back on")

    # Zod measures JavaScript strings in UTF-16 code units, not code points.
    if len(readme.encode("utf-16-le")) // 2 > 100_000:
        fail(f"{readme_path} exceeds the API's 100,000-character README limit")

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
    if len(zips) != 1:
        fail("Release must have exactly one source ZIP asset")
    history = fetch_existing_releases(ext_id)
    artifact = build_package(meta, zips[0])
    download_url = artifact["download_url"]

    # The API keys releases by plain semver version, not by git tag:
    # sorting, latest-release resolution, and the directory's edit form
    # all compare `tag` with semver. The git tag stays reachable through
    # the changelog and download URLs.
    new_release: dict = {
        "tag": version,
        "date": published_at[:10] if published_at else "",
        "download_url": download_url,
        "requires": requires,
        "artifact_id": artifact["id"],
        "sha256": artifact["sha256"],
    }
    if html_url:
        new_release["changelog_url"] = html_url

    other_releases = [entry for entry in history or [] if entry.get("tag") != version]
    # Stable publishes become latest. Prereleases retain an existing selection.
    previous = next((entry for entry in other_releases if entry.get("is_latest")), None)
    previous = previous or next((entry for entry in other_releases if "-" not in entry["tag"].split("+", 1)[0]), None) or next(iter(other_releases), None)
    selected_manifest = meta
    current = next((entry for entry in history or [] if entry.get("tag") == version), None)
    if (current and current.get("is_latest")) or "-" not in version.split("+", 1)[0] or previous is None:
        new_release["is_latest"] = True
    else:
        selected_manifest = api_json(f"/packages/{previous['artifact_id']}")["manifest"]
        previous["is_latest"] = True
    content = {key: value for key, value in selected_manifest.items() if key != "id"}
    content.update({
        "releases": merge_releases(new_release, history or []),
        "readme": readme,
        "source": {"type": "github", "repo": os.environ.get("GITHUB_REPOSITORY", "FOSSBilling/modules")},
    })
    selected_release = next(entry for entry in content["releases"] if entry.get("is_latest"))
    content["version"] = selected_release["tag"]
    content["download_url"] = selected_release["download_url"]

    create_content = dict(content)
    create_content["id"] = ext_id

    size = len(json.dumps(create_content, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    if size > MAX_CONTENT_BYTES:
        fail("Built payload exceeds the 256 KiB content limit")

    with open("payload-create.json", "w", encoding="utf-8") as handle:
        json.dump(create_content, handle, ensure_ascii=False, separators=(",", ":"))
    with open("payload-update.json", "w", encoding="utf-8") as handle:
        json.dump(content, handle, ensure_ascii=False, separators=(",", ":"))
    with open("payload-target.json", "w") as handle:
        json.dump({"exists": history is not None}, handle)
    print(f"Built payloads for {ext_id} {version} ({size} bytes)")


if __name__ == "__main__":
    main()
