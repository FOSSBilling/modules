"""Execute the workflow's submit shell offline against scripted API replies."""
import json
import os
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
    return textwrap.dedent(block.split("        run: |\n", 1)[1])


class ReleaseTargetTests(unittest.TestCase):
    def test_valid_tags_preserve_prereleases_and_build_metadata(self):
        for version in ["1.2.3", "1.2.3-v1.0.0", "1.2.3-alpha.1+build.4"]:
            self.assertEqual(parse_release_tag(f"example_module-v{version}"), ("example_module", version))

    def test_invalid_tags_are_rejected_before_outputs_or_checkout(self):
        for tag in ["example-v01.2.3", "example-v1.2.3\nother=value", "example-v1.2.3;echo bad", "EXAMPLE-v1.2.3", "../example-v1.2.3"]:
            with self.subTest(tag=tag), self.assertRaises(ValueError):
                parse_release_tag(tag)


class PublishWorkflowTests(unittest.TestCase):
    def run_submit(self, exists, replies, step="Submit revision (create or update)"):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "payload-target.json").write_text(json.dumps({"exists": exists}))
            (root / "replies.json").write_text(json.dumps(replies))
            (root / "payload-create.json").write_text('{}')
            (root / "payload-update.json").write_text('{}')
            curl = root / "curl"
            curl.write_text('''#!/usr/bin/env python3
import json, pathlib, sys
args = sys.argv[1:]
root = pathlib.Path('.')
replies = json.loads((root / 'replies.json').read_text())
response = replies.pop(0)
(root / 'replies.json').write_text(json.dumps(replies))
method = args[args.index('-X') + 1]
with open('calls.txt', 'a') as calls:
    calls.write(method + ' ' + args[-1] + '\\n')
assert method == response['method'], (method, response)
if '-o' in args:
    (root / args[args.index('-o') + 1]).write_text(json.dumps(response['body']))
    (root / args[args.index('-D') + 1]).write_text('Retry-After: 0\\n')
    print(response['code'], end='')
else:
    print(json.dumps(response['body']) + '\\n' + str(response['code']))
''')
            curl.chmod(0o755)
            env = {**os.environ, "PATH": f"{root}:{os.environ['PATH']}", "API_BASE_URL": "https://api.example.test/extensions/v2", "API_TOKEN": "offline", "EXT_ID": "example", "REVISION_ID": "revision", "GITHUB_OUTPUT": str(root / "outputs")}
            result = subprocess.run(["bash", "-e", "-o", "pipefail", "-c", workflow_run(step)], cwd=root, env=env, capture_output=True, text=True)
            calls = (root / 'calls.txt').read_text().splitlines()
            outputs = (root / 'outputs').read_text() if (root / 'outputs').exists() else ''
            return result, calls, outputs

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
