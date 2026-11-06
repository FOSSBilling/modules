"""Offline regression tests for release publishing; no credentials or network."""
import importlib.util
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("publisher", Path(__file__).with_name("build_payload.py"))
publisher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(publisher)


class PublisherTests(unittest.TestCase):
    def setUp(self):
        # Expected failures must not emit GitHub Actions error annotations.
        self.enterContext(redirect_stdout(io.StringIO()))
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.previous = os.getcwd()
        self.addCleanup(os.chdir, self.previous)
        os.chdir(self.temp.name)
        self.package = Path("Example_module")
        self.package.mkdir()
        self.meta = {
            "manifest_version": 1, "id": "example_module", "type": "module",
            "name": "Example", "description": "Example module", "version": "1.2.3",
            "author": {"name": "Author", "url": "https://example.com"},
            "license": "MIT OR Apache-2.0",
            "requires": {"fossbilling": "^0.8.9 || ^1.0", "php": ">=8.3 <9", "modules": {"branding": "^1.2"}},
        }
        (self.package / "README.md").write_text("# Example\n")
        self.release = {
            "published_at": "2026-11-04T00:00:00Z", "html_url": "https://github.com/FOSSBilling/modules/releases/tag/example_module-v1.2.3",
            "assets": [{"name": "example.zip", "browser_download_url": "https://github.com/FOSSBilling/modules/releases/download/example_module-v1.2.3/example.zip"}],
        }

    def build(self, history=None):
        (self.package / "manifest.json").write_text(json.dumps(self.meta))
        with patch.dict(os.environ, {"GITHUB_REPOSITORY": "FOSSBilling/modules"}), patch.object(publisher.sys, "argv", ["build_payload.py", "example_module", self.meta["version"], "example_module-v" + self.meta["version"]]), patch.object(publisher.subprocess, "run", return_value=SimpleNamespace(stdout=json.dumps(self.release))), patch.object(publisher, "fetch_existing_releases", return_value=history), patch.object(publisher, "build_package", return_value={"id": "134cf413-b5ab-4f57-b2ad-520020af880d", "sha256": "a" * 64, "manifest": dict(self.meta), "download_url": "https://api.example.test/extensions/v2/packages/134cf413-b5ab-4f57-b2ad-520020af880d/download"}):
            publisher.main()
        return json.loads(Path("payload-create.json").read_text()), json.loads(Path("payload-update.json").read_text())

    def test_preserves_manifest_metadata_and_compound_requirements(self):
        create, update = self.build()
        for field in self.meta:
            self.assertEqual(create[field], self.meta[field])
        self.assertNotIn("website", create)
        self.assertNotIn("homepage_url", create)
        self.assertNotIn("id", update)
        self.assertEqual(create["releases"][0]["requires"], self.meta["requires"])
        self.assertNotIn("min_fossbilling_version", create["releases"][0])
        self.assertEqual(create["readme"], "# Example\n")
        self.assertEqual(create, {**update, "id": "example_module"})

    def test_release_references_the_directory_built_package(self):
        create, _ = self.build([{ "tag": "1.0.0", "is_latest": True, "artifact_id": "old", "sha256": "b" * 64, "requires": self.meta["requires"] }])
        release = create["releases"][0]
        self.assertEqual(release["artifact_id"], "134cf413-b5ab-4f57-b2ad-520020af880d")
        self.assertEqual(release["sha256"], "a" * 64)
        self.assertTrue(release["is_latest"])
        self.assertEqual(create["download_url"], release["download_url"])
        self.assertNotIn("is_latest", create["releases"][1])
        self.assertEqual(create["releases"][1]["artifact_id"], "old")

    def test_prerelease_preserves_the_selected_managed_manifest_and_download(self):
        old = {**self.meta, "version": "1.0.0", "description": "Stable listing"}
        self.meta["version"] = "1.3.0-beta.1"
        history = [{"tag": "1.0.0", "date": "2026-01-01", "download_url": "https://api.example.test/stable.zip", "artifact_id": "old-artifact", "sha256": "b" * 64, "requires": old["requires"], "is_latest": True}]
        with patch.object(publisher, "api_json", return_value={"manifest": old}):
            create, _ = self.build(history)
        self.assertEqual(create["version"], "1.0.0")
        self.assertEqual(create["description"], "Stable listing")
        self.assertEqual(create["download_url"], history[0]["download_url"])
        self.assertNotIn("is_latest", create["releases"][0])
        self.assertTrue(create["releases"][1]["is_latest"])

    def test_optional_homepage_without_icon_metadata(self):
        self.meta["homepage_url"] = "https://example.com"
        create, _ = self.build()
        self.assertEqual(create["homepage_url"], "https://example.com")
        self.assertNotIn("icon_url", create)

    def test_icons_are_discovered_without_manifest_metadata(self):
        for format in ("svg", "png", "webp", "avif"):
            icon = self.package / f"icon.{format}"
            icon.write_text("image bytes")
            try:
                create, _ = self.build()
                self.assertNotIn("icon_url", create)
            finally:
                icon.unlink()

    def test_rejects_duplicate_icons_and_manifest_icon_field(self):
        (self.package / "icon.svg").write_text("svg")
        (self.package / "icon.png").write_text("png")
        with self.assertRaises(SystemExit):
            self.build()
        (self.package / "icon.png").unlink()
        self.meta["icon_url"] = "icon.svg"
        with self.assertRaises(SystemExit):
            self.build()

    def test_reruns_replace_the_same_version_and_preserve_other_requirements(self):
        old = {"tag": "1.0.0", "date": "2026-01-01", "download_url": "https://example.com/old.zip", "requires": {"fossbilling": "~0.7", "php": "^8.2", "modules": {"old": "^1"}}}
        create, _ = self.build([{"tag": "example_module-v1.2.3"}, old])
        self.assertEqual([entry["tag"] for entry in create["releases"]], ["1.2.3", "1.0.0"])
        self.assertEqual(create["releases"][1], old)

    def test_requires_a_distributable_and_matching_version(self):
        self.release["assets"] = []
        with self.assertRaises(SystemExit):
            self.build()
        self.meta["version"] = "2.0.0"
        with self.assertRaises(SystemExit):
            self.build()

    def test_readme_limit_matches_api_utf16_length(self):
        (self.package / "README.md").write_text("x" * 100_001)
        with self.assertRaises(SystemExit):
            self.build()
        (self.package / "README.md").write_text("😀" * 50_001)
        with self.assertRaises(SystemExit):
            self.build()
        (self.package / "README.md").write_text("😀" * 50_000)
        self.build()

    def test_target_comes_from_the_history_read(self):
        self.build()
        self.assertEqual(json.loads(Path("payload-target.json").read_text()), {"exists": False})
        self.build([{"tag": "1.0.0", "requires": self.meta["requires"]}])
        self.assertEqual(json.loads(Path("payload-target.json").read_text()), {"exists": True})

    def test_requires_php(self):
        del self.meta["requires"]["php"]
        with self.assertRaises(SystemExit):
            self.build()

    def test_release_cap_is_preserved(self):
        history = [{"tag": f"0.0.{index}"} for index in range(101)]
        self.assertEqual(len(self.build(history)[0]["releases"]), 100)

    def test_fetch_only_treats_404_as_a_new_extension(self):
        for code in [404, 401, 429, 500]:
            error = publisher.urllib.error.HTTPError("https://api.example.test", code, "error", {}, None)
            self.addCleanup(error.close)
            with self.subTest(code=code), patch.dict(os.environ, {"API_TOKEN": "test", "API_BASE_URL": "https://api.example.test"}), patch.object(publisher.urllib.request, "urlopen", side_effect=error):
                if code == 404:
                    self.assertIsNone(publisher.fetch_existing_releases("example"))
                else:
                    with self.assertRaises(SystemExit):
                        publisher.fetch_existing_releases("example")

    def test_fetch_retains_requires_and_rejects_pre_migration_history(self):
        requirements = {"fossbilling": "^0.8 || ^1", "php": "^8", "modules": {"branding": "*"}}
        entry = {"tag": "1.0.0", "requires": requirements, "unknown": "ignored"}
        with patch.dict(os.environ, {"API_TOKEN": "test", "API_BASE_URL": "https://api.example.test"}), patch.object(publisher.urllib.request, "urlopen", return_value=io.StringIO(json.dumps({"result": {"releases": [entry]}}))):
            self.assertEqual(publisher.fetch_existing_releases("example"), [{"tag": "1.0.0", "requires": requirements}])
        with patch.dict(os.environ, {"API_TOKEN": "test", "API_BASE_URL": "https://api.example.test"}), patch.object(publisher.urllib.request, "urlopen", return_value=io.StringIO(json.dumps({"result": {"releases": [{"tag": "old", "min_fossbilling_version": "0.6"}]}}))):
            with self.assertRaises(SystemExit):
                publisher.fetch_existing_releases("example")




class PackageApiTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(redirect_stdout(io.StringIO()))
        self.enterContext(patch.dict(os.environ, {"API_TOKEN": "test-token", "API_BASE_URL": "https://api.example.test/extensions/v2", "GITHUB_REPOSITORY": "FOSSBilling/modules"}))
        self.manifest = {"manifest_version": 1, "id": "example", "version": "1.0.0"}
        self.artifact = {"id": "134cf413-b5ab-4f57-b2ad-520020af880d", "sha256": "a" * 64, "manifest": self.manifest, "download_url": "https://api.example.test/extensions/v2/packages/134cf413-b5ab-4f57-b2ad-520020af880d/download"}
        self.source = "https://github.com/FOSSBilling/modules/releases/download/example-v1.0.0/source.zip"

    def test_uploads_the_exact_source_and_manifest_with_auth_only_on_the_api_call(self):
        calls = []
        def open_url(request, **kwargs):
            calls.append(request)
            return io.BytesIO(b"source ZIP" if isinstance(request, str) else json.dumps({"result": self.artifact}).encode())
        with patch.object(publisher.urllib.request, "urlopen", side_effect=open_url):
            self.assertEqual(publisher.build_package(self.manifest, self.source), self.artifact)
        self.assertEqual(calls[0], self.source)
        self.assertEqual(calls[1].full_url, "https://api.example.test/extensions/v2/packages")
        self.assertEqual(calls[1].get_header("Authorization"), "Bearer test-token")
        self.assertIn(b'name="manifest"', calls[1].data)
        self.assertIn(json.dumps(self.manifest).encode(), calls[1].data)
        self.assertIn(b"source ZIP", calls[1].data)

    def test_rejects_oversized_sources_before_uploading(self):
        with patch.object(publisher.urllib.request, "urlopen", return_value=io.BytesIO(b"x" * (5 * 1024 * 1024 + 1))) as request:
            with self.assertRaises(SystemExit):
                publisher.build_package(self.manifest, self.source)
        self.assertEqual(request.call_count, 1)

    def test_rejects_mismatched_artifact_metadata_and_foreign_download_urls(self):
        for replacement in [{"manifest": {}}, {"sha256": "invalid"}, {"download_url": "https://other.test/package.zip"}]:
            artifact = {**self.artifact, **replacement}
            with self.subTest(replacement=replacement), patch.object(publisher.urllib.request, "urlopen", return_value=io.BytesIO(b"ZIP")), patch.object(publisher, "api_json", return_value=artifact), self.assertRaises(SystemExit):
                publisher.build_package(self.manifest, self.source)

if __name__ == "__main__":
    unittest.main()
