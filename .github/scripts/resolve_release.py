"""Resolve a release tag without interpolating user input into shell code."""
import json
import os
from pathlib import Path
import re


SCHEMA = json.loads((Path(__file__).resolve().parents[2] / "manifest.schema.json").read_text())


def parse_release_tag(tag: str) -> tuple[str, str]:
    match = re.fullmatch(r"([a-z0-9_-]{1,64})-v(.+)", tag)
    if not match or len(match[2]) > 100 or not re.fullmatch(SCHEMA["properties"]["version"]["pattern"], match[2]):
        raise ValueError("Release tag must match <extension-id>-v<semver>")
    return match[1], match[2]


def main() -> None:
    tag = os.environ["RELEASE_TAG"]
    ext_id, version = parse_release_tag(tag)
    with open(os.environ["GITHUB_OUTPUT"], "a") as output:
        output.write(f"tag={tag}\nextension_id={ext_id}\nversion={version}\n")
    print(f"Publishing {ext_id} version {version}")


if __name__ == "__main__":
    main()
