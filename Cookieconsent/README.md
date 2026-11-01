# Cookie Consent

Shows a dismissible cookie-consent banner to help comply with the European
cookie law.

The message is configurable from the admin area (Extensions → Cookie
Consent) and is served through the `guest.cookieconsent_message` API. Once
dismissed, the choice is remembered in the visitor's browser via
`localStorage`, so the banner stays hidden on later visits.

First-party FOSSBilling module. Install it from the extensions directory,
then edit the message text to suit your site.
