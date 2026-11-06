# Apple pickup stock monitor

Checks Apple's pickup inventory for **iPhone Duo, 256GB, either color** (Star White `MK1E4LL/A` or Night Sky `MK1F4LL/A`) using **Santa Clara ZIP 95050**. The part number matches current third-party retail listings, but Apple checkout is the authority for unlocked/Connect Later eligibility.

## What gets checked

The Apple pickup API returns nearby Apple Stores for ZIP **95050**. The monitor checks **every store returned** for both 256GB part numbers and logs each store name and number in the GitHub Actions run. It does not search all Bay Area stores or restrict to a single store.

Checks are triggered by the external scheduler configured for this repository; GitHub Actions may start late or fail, and inventory may disappear between checks. The API is unofficial and may change. **Polling cannot guarantee detecting a short-lived restock.**

## What the email contains

When a store newly becomes available, the email names the store and includes a **Google Maps directions/search link** and [Apple's iPhone Duo order page](https://www.apple.com/shop/buy-iphone/iphone-duo). The link opens Apple's product page, not a reserved cart. Choose the available color shown in the email, 256GB, pickup at the listed store, and verify unlocked/Connect Later at checkout. No email is sent on repeated checks while the same color remains continuously available at a store. Each store/color combination is tracked separately, so a newly available second color also triggers an alert. If a color sells out and restocks, another alert is sent.

## Email configuration

Configure GitHub Actions secrets: `SMTP_HOST=smtp.mail.yahoo.com`, `SMTP_USER` (full authorized Yahoo sender address), `SMTP_PASSWORD` (Yahoo app password), `ALERT_EMAIL` (recipient). Optional `SMTP_PORT` defaults to **465 (implicit TLS)**; 587 uses STARTTLS. Never commit secrets.

## Tests

In Actions → Apple pickup stock monitor → Run workflow:

- **Validate only** (default): check live Apple inventory and log which stores are returned, no email.
- **Test email**: test Yahoo SMTP.
- **Simulate available**: send a clearly marked *simulated* stock alert showing the real email format without pretending stock exists or modifying state.

The workflow runs unit tests and stores the previous inventory in a GitHub release asset. If the saved state cannot be restored, the job fails rather than silently losing its deduplication history. On a scheduled failure, it attempts to email a failure notice. This cannot notify about jobs GitHub never starts, and a broken SMTP service can also prevent failure emails.

View [workflow runs](https://github.com/alissaahodge/apple-stock-monitor/actions).
