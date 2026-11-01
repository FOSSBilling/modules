# FOSSBilling modules

First-party extensions, published to the catalogue at
[extensions.fossbilling.org](https://extensions.fossbilling.org) by CI.

## Layout

One directory per extension. The directory name is the catalogue id
(lowercase, e.g. `paypal/`):

```
paypal/
  fossbilling.json   # catalogue metadata (required)
  README.md          # becomes the catalogue readme (required by default)
  src/ ...           # the module itself, plus a .zip release asset
```

## Releasing

Tag the release `<extension-id>-v<semver>` (e.g. `paypal-v1.2.0`) and attach
the distributable `.zip` as a release asset. Publishing a release runs
`.github/workflows/publish.yml`, which submits the new version to the
extensions API and approves it. A manual run is available via
`workflow_dispatch` with the same tag.

`fossbilling.json` fields:

| Field | Required | Notes |
| --- | --- | --- |
| `type` | yes | `mod`, `theme`, `payment-gateway`, `server-manager`, `domain-registrar`, `hook`, or `translation` |
| `name` | yes | Display name, max 120 chars |
| `description` | yes | Max 4000 chars |
| `website` | yes | `https://` URL |
| `license` | yes | `{ "name": "..." }`, plus optional `spdx_id` / `url` |
| `source` | yes | `{ "type": "github", "repo": "FOSSBilling/modules" }` |
| `min_fossbilling_version` | yes | e.g. `"0.7"` |
| `icon_url` | no | `https://` URL |
| `readme_file` | no | Defaults to `README.md` in the extension dir |
| `download_url` | no | Defaults to the release's first `.zip` asset. Supports `{tag}` and `{version}` placeholders |

The release tag becomes the catalogue release entry: date and changelog link
come from the GitHub release itself.

## Secrets

| Secret | Purpose |
| --- | --- |
| `MODULES_PUBLISHER_CLIENT_ID` | OAuth client id from `auth.fossbilling.net` |
| `MODULES_PUBLISHER_CLIENT_SECRET` | Its `fba_cs_` secret |

The client authenticates with `client_credentials` and is bound to the
`fossbilling` developer profile with publish rights (see the API repo's
extensions v2 README, "Machine publishing"). If a publish fails with 409,
a revision is already pending review — a moderator resolves it in the
review queue, then re-run the workflow.
