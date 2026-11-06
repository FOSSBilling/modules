# FOSSBilling Modules

First-party extensions, published to the extensions directory at
[extensions.fossbilling.org](https://extensions.fossbilling.org) by CI.

## Layout

One directory per extension, named `Ucfirst(id)` to match the installed
layout (`Branding/` for id `branding`):

```text
Branding/
  manifest.json   # module manifest, v1 spec (required)
  README.md       # becomes the extensions directory readme (required)
  Service.php, Api/, Controller/, templates/, icon.svg, ...
```

`manifest.json` follows the v1 spec (`manifest_version: 1`,
`type: "module"`). The canonical spec is
[`manifest.schema.json`](./manifest.schema.json); every package is
validated against it (plus semantic checks in `tools/validate.php`) by CI.

## Releasing

Tag the release `<extension-id>-v<semver>` (e.g. `branding-v0.8.9`, version
matching the package's `manifest.json`) and attach the distributable
`.zip` as a release asset. The zip must contain the package directory
contents at the archive root, with no wrapper folder, so it installs as-is.
Publishing runs the trusted tooling from `.github/workflows/publish.yml` against
package metadata checked out from the release tag. It uploads the single GitHub
ZIP asset and manifest to `POST /packages`; the directory builds the distributable
and returns an immutable artifact ID, SHA-256 and download URL. The submitted
release references those values, preserving earlier managed artifacts and
external release history. The workflow then approves the revision using its
existing `extensions:publish` permission.

Deploy the package-enabled Extensions v2 API before using this publisher in
production. The machine client must have
`extensions:push`, an active developer mapping and permission to publish for the
same developer. Package ZIPs remain private until the revision is approved.

Stable releases become the selected latest release. Prereleases retain the
previous managed selection when one exists; the listing's manifest metadata
continues to describe that selected package. A rerun of a version must upload
identical source bytes. The API reuses an identical artifact and rejects changed
source bytes for that version. Publish changed files under a new version.

The publisher refuses source ZIPs over 5 MiB, ambiguous releases with multiple ZIP
assets, unexpected artifact URLs and mismatched manifests. FOSSBilling, PHP and
module constraints remain unchanged. Existing release history may omit PHP;
new module manifests must still declare it. The readme, source and changelog links
remain directory metadata outside the generated manifest.

Publishing reads existing public release history before submitting. A public
404 may mean a delisted or unpublished extension: a subsequent create conflict
stops publishing rather than switching to an update without that history.
Resolve the pending or hidden listing before retrying.

## Secrets

The publisher credentials live in the `production`
[environment](https://github.com/FOSSBilling/modules/settings/environments),
not as repository secrets:

| Secret | Purpose |
| --- | --- |
| `MODULES_PUBLISHER_CLIENT_ID` | OAuth client id from `auth.fossbilling.net` |
| `MODULES_PUBLISHER_CLIENT_SECRET` | Its `fba_cs_` secret |

Every publish run waits for an approval from a designated reviewer before
the job executes. That is deliberate: the workflow runs code from the
triggering ref, so without the gate a collaborator could dispatch a
modified workflow from another branch and exfiltrate the credentials.
Approve a run only after checking which tag and ref it is publishing.

The client authenticates with `client_credentials` and is bound to the
`fossbilling` developer profile with publish rights (see the API repo's
extensions v2 README, "Machine publishing"). If a publish fails with 409,
a revision is already pending review — a moderator resolves it in the
review queue, then re-run the workflow.

Extension icons are discovered at the package root: include one of `icon.svg`, `icon.png`, `icon.webp`, or `icon.avif`. Omit the icon for the generic fallback. Icon filenames are not declared in `manifest.json`.
