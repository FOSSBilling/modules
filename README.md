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
  icon.svg        # optional package icon; at most one of icon.svg, icon.png, icon.webp, icon.avif
  Service.php, Api/, Controller/, templates/, ...
```

`manifest.json` follows the v1 spec (`manifest_version: 1`,
`type: "module"`). The canonical spec is
[`manifest.schema.json`](./manifest.schema.json); every package is
validated against it (plus semantic checks via `tools/bin/console manifest:validate`) by CI.

## Releasing

Tag the release `<extension-id>-v<semver>` (e.g. `branding-v0.8.9`, version
matching the package's `manifest.json`) and attach the distributable
`.zip` as a release asset. The zip must contain the package directory
contents at the archive root, with no wrapper folder, so it installs as-is.
Publishing a release runs `.github/workflows/publish.yml`, which sends the manifest v1 fields directly to the extensions API and approves the new revision. `type: "module"`, string licenses, optional `homepage_url`, author metadata, and the complete `requires` object are preserved. A manual run is available via `workflow_dispatch` with the same tag. Both triggers read package files from that tag, while using publisher tooling from the reviewed workflow ref.

FOSSBilling, PHP, and module constraints are retained verbatim, including compound Composer ranges. Each release stores its own requirements. Deploy the API manifest migration and matching extensions site before running this publisher; it refuses history without `requires` instead of discarding compatibility information.

The release becomes a new extensions directory release entry keyed by the version:
date, changelog link, and the distributable asset come from the GitHub
release itself, and the entry is prepended to the extension's release
history. A manual re-run via `workflow_dispatch` with the same tag
replaces the entry in place. A public 404 can also mean a delisted or unpublished extension: if creation then conflicts, publishing stops for manual correction instead of updating without its release history. Once the extension is public, retry to fetch its history first.

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

Directory creation sends the manifest’s public `id` as `identifier`. Developer
publisher bindings use the UUID `id` returned by the developer profile API.
