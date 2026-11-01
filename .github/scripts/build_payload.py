"""Build the extensions API content payload for one release.

Reads <extension_id>/fossbilling.json plus the extension README, resolves
the download URL from the GitHub release's .zip asset (unless the manifest
overrides it), and writes the API content object to payload.json.

Usage: build_payload.py <extension_id> <version> <tag>
"""

import json
import os
import subprocess
import sys


MAX_CONTENT_BYTES = 256 * 1024


def fail(message: str) -> None:
    print(f"::error::{message}", flush=True)
    sys.exit(1)


def main() -> None:
    ext_id, version, tag = sys.argv[1], sys.argv[2], sys.argv[3]
    meta_path = os.path.join(ext_id, "fossbilling.json")
    if not os.path.isfile(meta_path):
        fail(f"{meta_path} not found")

    meta = json.load(open(meta_path))
    for field in (
        "type",
        "name",
        "description",
        "website",
        "license",
        "source",
        "min_fossbilling_version",
    ):
        if field not in meta:
            fail(f"{meta_path} is missing required field '{field}'")

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

    download_url = meta.get("download_url")
    if download_url:
        download_url = download_url.replace("{tag}", tag).replace("{version}", version)
    else:
        zips = [
            a["browser_download_url"]
            for a in release.get("assets", [])
            if a.get("name", "").endswith(".zip")
        ]
        if not zips:
            fail("Release has no .zip asset and fossbilling.json sets no download_url")
        download_url = zips[0]

    readme_file = meta.get("readme_file", "README.md")
    readme_path = os.path.join(ext_id, readme_file)
    if not os.path.isfile(readme_path):
        fail(f"{readme_path} not found")
    readme = open(readme_path).read()
    if not readme.strip():
        fail(f"{readme_path} is empty")

    new_release: dict = {
        "tag": tag,
        "date": published_at,
        "download_url": download_url,
        "min_fossbilling_version": meta["min_fossbilling_version"],
    }
    if html_url:
        new_release["changelog_url"] = html_url

    content: dict = {
        "type": meta["type"],
        "name": meta["name"],
        "description": meta["description"],
        "releases": [new_release],
        "website": meta["website"],
        "license": meta["license"],
        "readme": readme,
        "source": meta["source"],
        "version": version,
        "download_url": download_url,
    }
    if meta.get("icon_url"):
        content["icon_url"] = meta["icon_url"]

    size = len(json.dumps(content).encode())
    if size > MAX_CONTENT_BYTES:
        fail("Built payload exceeds the 256 KiB content limit")

    with open("payload.json", "w") as handle:
        json.dump(content, handle)
    print(f"Built payload for {ext_id} {version} ({size} bytes)")


main()
