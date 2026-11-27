# AcoreHost

AcoreHost task source lives only on this independent branch. Workflow remains on main at `.github/workflows/renew_acorehost.yml`.

- This is an isolation migration: no renewal, startup or schedule policy changed.
- API key comes from `ACORE_API_KEY` Actions secret; do not print credentials or commit session data.
- Known issue from prior inspection: the script can count renewal and running status twice for one server, causing a false failure. It also does not independently verify expiry after a renewal, and treats `starting` as alive. These issues have not been fixed in the isolation migration.
