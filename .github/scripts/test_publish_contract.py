"""Execute the workflow's submit shell offline against scripted API replies."""
import json
import os
import shutil
from pathlib import Path
import subprocess
import tempfile
import textwrap
import unittest

from resolve_release import parse_release_tag


ROOT = Path(__file__).resolve().parents[2]


def workflow_run(step):
    source = (ROOT / ".github/workflows/publish.yml").read_text()
    block = source.split(f"      - name: {step}\n", 1)[1].split("\n      - ", 1)[0]
    command = block.split("        run: ", 1)[1]
    return textwrap.dedent(command[2:]) if command.startswith("|\n") else command.splitlines()[0]


class ReleaseTargetTests(unittest.TestCase):
    def test_valid_tags_preserve_prereleases_and_build_metadata(self):
        for version in ["1.2.3", "1.2.3-v1.0.0", "1.2.3-alpha.1+build.4"]:
            self.assertEqual(parse_release_tag(f"example_module-v{version}"), ("example_module", version))

    def test_invalid_tags_are_rejected_before_outputs_or_checkout(self):
        for tag in ["example-v01.2.3", "example-v1.2.3\nother=value", "example-v1.2.3;echo bad", "EXAMPLE-v1.2.3", "../example-v1.2.3"]:
            with self.subTest(tag=tag), self.assertRaises(ValueError):
                parse_release_tag(tag)


class PublishWorkflowTests(unittest.TestCase):
    def run_submit(self, exists, replies, step="Submit revision (create or update)", hostile_module=None, after_api=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "payload-target.json").write_text(json.dumps({"exists": exists}))
            (root / "replies.json").write_text(json.dumps(replies))
            (root / "payload-create.json").write_text('{}')
            (root / "payload-update.json").write_text('{}')
            hostile_source = "from pathlib import Path\nPath('hostile-imported').write_text('executed')\nraise RuntimeError('tag-controlled import')\n"
            if hostile_module and not after_api:
                module = root / hostile_module
                module.parent.mkdir(parents=True, exist_ok=True)
                module.write_text(hostile_source)
            curl = root / "curl"
            curl.write_text('''#!/usr/bin/env -S python3 -I
import json, os, pathlib, sys
args = sys.argv[1:]
root = pathlib.Path('.')
replies = json.loads((root / 'replies.json').read_text())
response = replies.pop(0)
(root / 'replies.json').write_text(json.dumps(replies))
method = args[args.index('-X') + 1]
with open('calls.txt', 'a') as calls:
    calls.write(method + ' ' + args[-1] + '\\n')
assert method == response['method'], (method, response)
if os.environ.get('HOSTILE_MODULE'):
    module = root / os.environ['HOSTILE_MODULE']
    module.parent.mkdir(parents=True, exist_ok=True)
    module.write_text(os.environ['HOSTILE_SOURCE'])
if '-o' in args:
    (root / args[args.index('-o') + 1]).write_text(json.dumps(response['body']))
    (root / args[args.index('-D') + 1]).write_text('Retry-After: 0\\n')
    print(response['code'], end='')
else:
    print(json.dumps(response['body']) + '\\n' + str(response['code']))
''')
            curl.chmod(0o755)
            env = {**os.environ, "PATH": f"{root}:{os.environ['PATH']}", "API_BASE_URL": "https://api.example.test/extensions/v2", "API_TOKEN": "offline", "EXT_ID": "example", "REVISION_ID": "revision", "GITHUB_OUTPUT": str(root / "outputs")}
            if hostile_module and after_api:
                env.update({"HOSTILE_MODULE": hostile_module, "HOSTILE_SOURCE": hostile_source})
            result = subprocess.run(["bash", "-e", "-o", "pipefail", "-c", workflow_run(step)], cwd=root, env=env, capture_output=True, text=True)
            self.assertFalse((root / 'hostile-imported').exists(), 'Tagged content executed during JSON parsing')
            calls = (root / 'calls.txt').read_text().splitlines()
            outputs = (root / 'outputs').read_text() if (root / 'outputs').exists() else ''
            return result, calls, outputs

    def test_tagged_modules_cannot_hijack_either_submit_parser(self):
        for module in ["json.py", "json/__init__.py"]:
            for after_api in [False, True]:
                with self.subTest(module=module, after_api=after_api):
                    result, _, outputs = self.run_submit(False, [{"method": "POST", "code": 201, "body": {"result": {"revision_id": "revision", "status": "pending"}}}], hostile_module=module, after_api=after_api)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(outputs, 'revision_id=revision\n')

    def test_build_uses_trusted_sibling_imports_despite_pythonpath(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scripts = root / '.github/scripts'
            scripts.mkdir(parents=True)
            for name in ['build_payload.py', 'resolve_release.py']:
                shutil.copyfile(ROOT / '.github/scripts' / name, scripts / name)
            shutil.copyfile(ROOT / 'manifest.schema.json', root / 'manifest.schema.json')
            release = root / 'release-source'
            release.mkdir()
            package = release / 'Branding'
            package.mkdir()
            for name in ['manifest.json', 'README.md']:
                shutil.copyfile(ROOT / 'Branding' / name, package / name)
            version = json.loads((package / 'manifest.json').read_text())['version']
            (release / 'json.py').write_text("from pathlib import Path\nPath('hostile-imported').write_text('executed')\nraise RuntimeError('tag-controlled import')\n")
            bin_dir = root / 'bin'
            bin_dir.mkdir()
            gh = bin_dir / 'gh'
            gh.write_text('#!/usr/bin/env -S python3 -I\nprint(' + repr(json.dumps({"published_at": "2026-01-01", "assets": [{"name": "release.zip", "browser_download_url": "https://example.test/release.zip"}]})) + ')\n')
            gh.chmod(0o755)
            env = {**os.environ, 'PATH': f"{bin_dir}:{os.environ['PATH']}", 'PYTHONPATH': str(release), 'API_TOKEN': 'offline', 'API_BASE_URL': '', 'GITHUB_REPOSITORY': 'FOSSBilling/modules', 'EXT_ID': 'branding', 'VERSION': version, 'RELEASE_TAG': f'branding-v{version}'}
            result = subprocess.run(['bash', '-e', '-c', workflow_run('Build extension payload')], cwd=release, env=env, capture_output=True, text=True)
            self.assertFalse((release / 'hostile-imported').exists(), 'Tagged module imported via PYTHONPATH')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads((release / 'payload-create.json').read_text())['id'], 'branding')

    def test_create_and_update_accept_the_merged_api_statuses(self):
        for exists, method, code in [(False, "POST", 201), (True, "PUT", 202)]:
            with self.subTest(method=method):
                result, calls, outputs = self.run_submit(exists, [{"method": method, "code": code, "body": {"result": {"revision_id": "revision", "status": "pending"}}}])
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(len(calls), 1)
                self.assertEqual(outputs, 'revision_id=revision\n')

    def test_conflict_without_history_never_switches_to_update(self):
        result, calls, _ = self.run_submit(False, [{"method": "POST", "code": 409, "body": {"error": {"message": "An extension with this id already exists"}}}])
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(calls), 1)
        self.assertIn("refusing to overwrite releases", result.stdout)

    def test_explicit_machine_approval_matches_the_merged_api(self):
        for code in [200, 403, 409]:
            result, calls, _ = self.run_submit(True, [{"method": "POST", "code": code, "body": {"result": {"status": "approved"}}}], step="Approve revision")
            self.assertEqual(result.returncode == 0, code == 200, result.stderr)
            self.assertEqual(calls, ["POST https://api.example.test/extensions/v2/extensions/example/revisions/revision/approve?notify=false"])

    def test_retries_preserve_update_method_and_payload(self):
        result, calls, _ = self.run_submit(True, [{"method": "PUT", "code": 429, "body": {}}, {"method": "PUT", "code": 202, "body": {"result": {"revision_id": "revision", "status": "pending"}}}])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(calls), 2)


if __name__ == "__main__":
    unittest.main()
