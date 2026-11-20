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
from unittest.mock import call, patch

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

    def build(self, history=None, *, description=None, archive_manifest=None):
        (self.package / "manifest.json").write_text(json.dumps(self.meta))
        version = self.meta["version"]
        existing = {"releases": history, "description": description} if history is not None else None
        artifact = {
            "id": "134cf413-b5ab-4f57-b2ad-520020af880d",
            "sha256": "a" * 64,
            "manifest": archive_manifest if archive_manifest is not None else dict(self.meta),
            "download_url": "https://api.example.test/extensions/v2/packages/134cf413-b5ab-4f57-b2ad-520020af880d/download",
        }
        with (
            patch.dict(os.environ, {"GITHUB_REPOSITORY": "FOSSBilling/modules"}),
            patch.object(publisher.sys, "argv", ["build_payload.py", "example_module", version, f"example_module-v{version}"]),
            patch.object(publisher.subprocess, "run", return_value=SimpleNamespace(stdout=json.dumps(self.release))),
            patch.object(publisher, "fetch_existing_extension", return_value=existing),
            patch.object(publisher, "validate_package", return_value=artifact),
        ):
            publisher.main()
        return json.loads(Path("payload-create.json").read_text()), json.loads(Path("payload-update.json").read_text())

    def test_preserves_manifest_metadata_and_compound_requirements(self):
        create, update = self.build()
        self.assertEqual(create["identifier"], self.meta["id"])
        self.assertNotIn("id", create)
        self.assertNotIn("identifier", update)
        for field in self.meta:
            if field != "id":
                self.assertEqual(create[field], self.meta[field])
        self.assertNotIn("website", create)
        self.assertNotIn("homepage_url", create)
        self.assertNotIn("id", update)
        self.assertEqual(create["releases"][0]["requires"], self.meta["requires"])
        self.assertNotIn("min_fossbilling_version", create["releases"][0])
        self.assertEqual(create["readme"], "# Example\n")
        self.assertEqual(create, {**update, "identifier": "example_module"})

    def test_release_references_the_validated_upload(self):
        create, _ = self.build([{ "tag": "1.0.0", "is_latest": True, "artifact_id": "old", "sha256": "b" * 64, "requires": self.meta["requires"] }])
        release = create["releases"][0]
        self.assertEqual(release["artifact_id"], "134cf413-b5ab-4f57-b2ad-520020af880d")
        self.assertEqual(release["sha256"], "a" * 64)
        self.assertEqual(release["date"], self.release["published_at"][:10])
        self.assertTrue(release["is_latest"])
        self.assertEqual(create["download_url"], release["download_url"])
        self.assertNotIn("is_latest", create["releases"][1])
        self.assertEqual(create["releases"][1]["artifact_id"], "old")

    def test_uses_zip_metadata_and_preserves_an_existing_listing_description(self):
        archive_manifest = {**self.meta, "name": "From the ZIP", "requires": {"fossbilling": "^1.0", "php": "^8.4"}}
        (self.package / "README.md").unlink()
        create, _ = self.build(
            [{"tag": "1.0.0", "download_url": "https://example.test/old.zip", "requires": self.meta["requires"]}],
            description="Directory description",
            archive_manifest=archive_manifest,
        )
        self.assertEqual(create["name"], "From the ZIP")
        self.assertEqual(create["requires"], archive_manifest["requires"])
        self.assertEqual(create["releases"][0]["requires"], archive_manifest["requires"])
        self.assertEqual(create["description"], "Directory description")
        self.assertEqual(create["readme"], archive_manifest["description"])

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

    def test_retry_keeps_a_selected_prerelease_selected(self):
        self.meta["version"] = "1.3.0-beta.1"
        history = [
            {"tag": "1.3.0-beta.1", "artifact_id": "current", "is_latest": True},
            {"tag": "1.0.0", "artifact_id": "stable", "download_url": "https://example.test/stable.zip", "requires": self.meta["requires"]},
        ]
        create, _ = self.build(history)
        self.assertEqual(create["version"], "1.3.0-beta.1")
        self.assertTrue(create["releases"][0]["is_latest"])
        self.assertNotIn("is_latest", create["releases"][1])

    def test_release_limit_retains_the_selected_release(self):
        new = {"tag": "2.0.0-beta.1"}
        history = [{"tag": f"1.0.{i}"} for i in range(100)]
        history[-1]["is_latest"] = True
        merged = publisher.merge_releases(new, history)
        self.assertEqual(len(merged), 100)
        self.assertEqual(merged[0], new)
        self.assertIn(history[-1], merged)

    def test_prerelease_uses_its_own_manifest_when_only_external_releases_exist(self):
        self.meta["version"] = "1.3.0-beta.1"
        external = {
            "tag": "1.0.0",
            "date": "2026-01-01",
            "download_url": "https://example.test/old.zip",
            "requires": self.meta["requires"],
            "is_latest": True,
        }
        create, _ = self.build([external])
        self.assertEqual(create["version"], self.meta["version"])
        self.assertTrue(create["releases"][0]["is_latest"])
        self.assertEqual(create["releases"][1], {k: v for k, v in external.items() if k != "is_latest"})

    def test_reruns_replace_the_same_version_and_preserve_other_requirements(self):
        old = {"tag": "1.0.0", "date": "2026-01-01", "download_url": "https://example.com/old.zip", "requires": {"fossbilling": "~0.7", "php": "^8.2", "modules": {"old": "^1"}}}
        create, _ = self.build([{"tag": "1.2.3"}, old])
        self.assertEqual([entry["tag"] for entry in create["releases"]], ["1.2.3", "1.0.0"])
        self.assertEqual(create["releases"][1], old)

    def test_requires_a_distributable(self):
        self.release["assets"] = []
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

    def test_requires_php_in_the_zip_manifest(self):
        archive_manifest = {**self.meta, "requires": {"fossbilling": "^1.0"}}
        with self.assertRaises(SystemExit):
            self.build(archive_manifest=archive_manifest)

    def test_release_cap_is_preserved(self):
        history = [{"tag": f"0.0.{index}"} for index in range(101)]
        self.assertEqual(len(self.build(history)[0]["releases"]), 100)

    def test_fetch_only_treats_404_as_a_new_extension(self):
        for code in [404, 401, 429, 500]:
            error = publisher.urllib.error.HTTPError("https://api.example.test", code, "error", {}, None)
            self.addCleanup(error.close)
            with self.subTest(code=code), patch.dict(os.environ, {"API_TOKEN": "test", "API_BASE_URL": "https://api.example.test"}), patch.object(publisher.urllib.request, "urlopen", side_effect=error):
                if code == 404:
                    self.assertIsNone(publisher.fetch_existing_extension("example"))
                else:
                    with self.assertRaises(SystemExit):
                        publisher.fetch_existing_extension("example")

    def test_fetch_returns_current_release_fields_unchanged(self):
        entry = {"tag": "1.0.0", "requires": {"fossbilling": "^0.8", "php": "^8"}, "artifact_id": "package", "sha256": "a" * 64}
        with patch.dict(os.environ, {"API_TOKEN": "test", "API_BASE_URL": "https://api.example.test"}), patch.object(publisher.urllib.request, "urlopen", return_value=io.StringIO(json.dumps({"result": {"releases": [entry]}}))):
            self.assertEqual(publisher.fetch_existing_extension("example"), {"releases": [entry]})

    def test_missing_credentials_stop_history_reads(self):
        with patch.dict(os.environ, {"API_TOKEN": "", "API_BASE_URL": ""}), self.assertRaises(SystemExit):
            publisher.fetch_existing_extension("example")


class PackageApiTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(redirect_stdout(io.StringIO()))
        self.enterContext(patch.dict(os.environ, {"API_TOKEN": "test-token", "API_BASE_URL": "https://api.example.test/extensions/v2", "GITHUB_REPOSITORY": "FOSSBilling/modules"}))
        self.target = {"id": "example", "version": "1.0.0"}
        self.zip = b"source ZIP"
        self.checksum = publisher.hashlib.sha256(self.zip).hexdigest()
        self.artifact = {"id": "134cf413-b5ab-4f57-b2ad-520020af880d", "sha256": self.checksum, "manifest": {"manifest_version": 1, **self.target}, "download_url": "https://api.example.test/extensions/v2/packages/134cf413-b5ab-4f57-b2ad-520020af880d/download"}
        self.source = "https://github.com/FOSSBilling/modules/releases/download/example-v1.0.0/source.zip"

    def test_reserves_and_confirms_via_the_api_with_the_zip_sent_only_to_storage(self):
        calls = []
        upload_id = "33333333-3333-4333-8333-333333333333"
        job = {"id": "44444444-4444-4444-8444-444444444444", "extension_identifier": "example", "status": "ready", "artifact": self.artifact}
        upload_url = "https://storage.example.test/object?signature=test"

        def open_url(request, **kwargs):
            calls.append(request)
            if isinstance(request, str):
                return io.BytesIO(b"source ZIP")
            if request.get_method() == "PUT":
                return io.BytesIO()
            result = (
                {"kind": "upload", "id": upload_id, "url": upload_url, "headers": {"Content-Type": "application/zip"}}
                if request.full_url.endswith("/package-uploads")
                else job
            )
            return io.BytesIO(json.dumps({"result": result}).encode())

        with patch.object(publisher.urllib.request, "urlopen", side_effect=open_url):
            self.assertEqual(publisher.validate_package(self.target, self.source), self.artifact)
        download, reserve, upload, confirm = calls
        self.assertEqual(download, self.source)
        self.assertEqual(reserve.full_url, "https://api.example.test/extensions/v2/package-uploads")
        self.assertEqual(reserve.get_header("Authorization"), "Bearer test-token")
        self.assertEqual(json.loads(reserve.data), {
            "target": self.target, "bytes": len(b"source ZIP"),
            "sha256": publisher.hashlib.sha256(b"source ZIP").hexdigest(),
        })
        self.assertEqual(upload.full_url, upload_url)
        self.assertEqual(upload.get_method(), "PUT")
        self.assertEqual(upload.data, b"source ZIP")
        self.assertIsNone(upload.get_header("Authorization"))
        self.assertEqual(upload.get_header("Content-type"), "application/zip")
        self.assertEqual(confirm.full_url, "https://api.example.test/extensions/v2/packages")
        self.assertEqual(confirm.get_header("Authorization"), "Bearer test-token")
        self.assertEqual(json.loads(confirm.data), {"upload_id": upload_id})

    def test_polls_a_queued_package_before_returning_the_artifact(self):
        job = {"id": "44444444-4444-4444-8444-444444444444", "extension_identifier": "example", "status": "queued", "artifact": None}
        ready = {**job, "status": "ready", "artifact": self.artifact}
        with patch.object(publisher.urllib.request, "urlopen", return_value=io.BytesIO(self.zip)), patch.object(publisher, "api_json", side_effect=[{"kind": "job", "job": job}, {**job, "status": "processing"}, ready]) as request, patch.object(publisher.time, "sleep") as sleep:
            self.assertEqual(publisher.validate_package(self.target, self.source), self.artifact)
        self.assertEqual(request.call_args_list[-1].args, ("/packaging-jobs/" + job["id"],))
        self.assertEqual(sleep.call_args_list, [call(1), call(2)])

    def test_stops_polling_at_the_deadline(self):
        job = {"id": "44444444-4444-4444-8444-444444444444", "extension_identifier": "example", "status": "queued"}
        with patch.object(publisher.urllib.request, "urlopen", return_value=io.BytesIO(self.zip)), patch.object(publisher, "api_json", side_effect=[{"kind": "job", "job": job}, job]) as request, patch.object(publisher.time, "monotonic", side_effect=[0, 179, 179.5, 180]), patch.object(publisher.time, "sleep"):
            with self.assertRaises(SystemExit):
                publisher.validate_package(self.target, self.source)
        self.assertEqual(request.call_count, 2)
        self.assertEqual(request.call_args.kwargs, {"timeout": 0.5})

    def test_failed_job_stops_publishing(self):
        job = {"id": "44444444-4444-4444-8444-444444444444", "extension_identifier": "example", "status": "queued"}
        failed = {**job, "status": "failed", "error": {"message": "Invalid archive"}}
        with (
            patch.object(publisher.urllib.request, "urlopen", return_value=io.BytesIO(self.zip)),
            patch.object(publisher, "api_json", side_effect=[{"kind": "job", "job": job}, failed]) as request,
            patch.object(publisher.time, "sleep"),
            self.assertRaises(SystemExit),
        ):
            publisher.validate_package(self.target, self.source)
        self.assertEqual(request.call_args.args, ("/packaging-jobs/" + job["id"],))

    def test_failed_put_stops_before_confirmation(self):
        upload_url = "https://storage.example.test/object?signature=test"
        result = {"kind": "upload", "id": "33333333-3333-4333-8333-333333333333", "url": upload_url, "headers": {}}
        rejection = publisher.urllib.error.HTTPError(upload_url, 403, "Forbidden", {}, None)
        with (
            patch.object(publisher.urllib.request, "urlopen", side_effect=[io.BytesIO(self.zip), rejection]),
            patch.object(publisher, "api_json", return_value=result) as request,
            self.assertRaises(SystemExit),
        ):
            publisher.validate_package(self.target, self.source)
        request.assert_called_once()
        self.assertEqual(request.call_args.args[0], "/package-uploads")

    def test_rejects_oversized_sources_before_uploading(self):
        with patch.object(publisher.urllib.request, "urlopen", return_value=io.BytesIO(b"x" * (5 * 1024 * 1024 + 1))) as request:
            with self.assertRaises(SystemExit):
                publisher.validate_package(self.target, self.source)
        self.assertEqual(request.call_count, 1)

    def test_rejects_mismatched_artifact_metadata_and_foreign_download_urls(self):
        for replacement in [
            {"manifest": {"manifest_version": 1, **self.target, "version": "2.0.0"}},
            {"sha256": "0" * 64},
            {"download_url": "https://other.test/package.zip"},
        ]:
            artifact = {**self.artifact, **replacement}
            with self.subTest(replacement=replacement), patch.object(publisher.urllib.request, "urlopen", return_value=io.BytesIO(self.zip)), patch.object(publisher, "api_json", return_value={"kind":"job","job":{"id":"44444444-4444-4444-8444-444444444444","extension_identifier":"example","status":"ready","artifact":artifact}}), self.assertRaises(SystemExit):
                publisher.validate_package(self.target, self.source)

if __name__ == "__main__":
    unittest.main()
