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
            "license": "MIT OR Apache-2.0", "icon_url": "assets/icon.svg",
            "requires": {"fossbilling": "^0.8.9 || ^1.0", "php": ">=8.3 <9", "modules": {"branding": "^1.2"}},
        }
        (self.package / "README.md").write_text("# Example\n")
        self.release = {
            "published_at": "2026-11-04T00:00:00Z", "html_url": "https://github.com/FOSSBilling/modules/releases/tag/example_module-v1.2.3",
            "assets": [{"name": "example.zip", "browser_download_url": "https://github.com/FOSSBilling/modules/releases/download/example_module-v1.2.3/example.zip"}],
        }

    def build(self, history=None):
        (self.package / "manifest.json").write_text(json.dumps(self.meta))
        with patch.dict(os.environ, {"GITHUB_REPOSITORY": "FOSSBilling/modules"}), patch.object(publisher.sys, "argv", ["build_payload.py", "example_module", "1.2.3", "example_module-v1.2.3"]), patch.object(publisher.subprocess, "run", return_value=SimpleNamespace(stdout=json.dumps(self.release))), patch.object(publisher, "fetch_existing_releases", return_value=history):
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

    def test_optional_homepage_and_icon(self):
        self.meta["homepage_url"] = "https://example.com"
        del self.meta["icon_url"]
        create, _ = self.build()
        self.assertEqual(create["homepage_url"], "https://example.com")
        self.assertNotIn("icon_url", create)

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


if __name__ == "__main__":
    unittest.main()
