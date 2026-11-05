# Apple Stock Monitor

Checks Apple's US Apple Store pickup inventory for **iPhone Duo, Star White, 256GB only**, near Sunnyvale, California (ZIP 94086). Uses Python standard library and GitHub Actions.

## Product

- Color: **Star White**
- Storage: **256GB only**
- US part number: `MK1E4LL/A` (provisional until Apple's live listing can be confirmed)
- Desired purchase: **factory unlocked / connect later**. The checker filters by part number; verify unlocked terms at checkout.
- Apple product page: https://www.apple.com/shop/buy-iphone/iphone-duo

## Important status

The GitHub Actions workflow checks every five minutes **on a best-effort schedule**. Scheduled runs are configured to check stock and send alerts after merge, but will fail until email secrets are configured and Apple's endpoint is confirmed reachable from GitHub-hosted runners. Before enabling email alerts, we must verify Apple's inventory response works on GitHub-hosted runners and the SMTP test succeeds. Apple's cloud-IP restrictions may prevent GitHub Actions from reaching the endpoint. Errors are reported as errors, never as a 'sold out' result.

## Email setup

Set repository Actions secrets under **Settings → Secrets and variables → Actions**:
- `SMTP_HOST` (e.g. `smtp.gmail.com`)
- `SMTP_USER` (sender email)
- `SMTP_PASSWORD` (app password or mail provider token; not your regular password)
- `ALERT_EMAIL` (recipient)
- Optional `SMTP_PORT` (default 587)

Do not commit credentials.

## Testing and activation

1. Run `python -m unittest discover -s tests -v` locally.
2. After merge, go to **Actions → Apple pickup stock monitor → Run workflow** and leave `validate_only` enabled. Check logs for `Validated Apple response`.
3. With SMTP secrets configured, run the workflow with `test_email=true` to verify email delivery.
4. **Only after both validations**, scheduled runs now invoke the stock checker and persist alert state using a GitHub release asset. If Apple's endpoint rejects GitHub runners, switch to an allowed runtime rather than treating the failure as sold out.
5. Inspect the actual Apple checkout page before purchasing.

The endpoint `https://www.apple.com/shop/fulfillment-messages` is unofficial and may change or block GitHub runners. A five-minute schedule may also be delayed or skipped.
