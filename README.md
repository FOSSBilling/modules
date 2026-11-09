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

## Translations

Module translations will use a separate **FOSSBilling Modules** Crowdin project, starting with Branding and Cookieconsent. The inactive [configuration example](./crowdin.example.yml) keeps each module's template and translations together:

```text
Branding/locale/branding.pot
Branding/locale/<locale>/LC_MESSAGES/branding.po
Cookieconsent/locale/cookieconsent.pot
Cookieconsent/locale/<locale>/LC_MESSAGES/cookieconsent.po
```

Use the existing [translation tooling](https://github.com/FOSSBilling/FOSSBilling/blob/main/tools/i18n/README.md) to extract, validate and compile translations.

The example needs `CROWDIN_MODULES_PROJECT_ID` and `CROWDIN_MODULES_PERSONAL_TOKEN` for the separate Modules project. Existing core project 4 remains owned by `FOSSBilling/locale`.

Before activation, create the Modules project, review source and target languages, translator access and shared translation memory, and import and validate the existing translations. Carry out that one-time migration directly. PO imports do not preserve Crowdin approval state or full history; retain the original project for attribution and review imports before approval.

The example is not read by a workflow. Installing it as `crowdin.yml`, connecting Crowdin and enabling synchronization are separate activation steps. Module releases and publication remain separate from this configuration preparation.

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
