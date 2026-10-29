# Changelog

All notable changes to ChartHawk are documented here.

## 2026-10-29

### Added
- **Privacy policy in its own file**, `web_app/templates/partials/privacy_policy.html`. The home page pop-up and a new `/privacy` page both use it, so the policy is edited in one place. The dashboard footer now links to `/privacy`.
- **Terms of Service in its own file**, `web_app/templates/partials/terms_of_service.html`. The "accept the terms" pop-ups on the home page and the dashboard, and a new `/terms` page, all use it. The footer "Terms of Service" links on the home page, dashboard and privacy page open `/terms`.
- Terms rewritten to cover all four AI companies and their usage policies, public sharing and comments, acceptable use, API keys, liability and how the terms change. `TOS_VERSION` raised from `v1` to `v1.1`, so everyone is asked to accept the new terms at their next sign-in.
- **New chart composer on the landing page**, in the style of Claude, Gemini and Perplexity. You attach a chart first (it shows as a removable thumbnail) and then send it, optionally with a question that's asked as the first follow-up once the analysis is ready.
  - A + menu with "Upload from computer", "Paste a screenshot" and "Add from a link". Google Drive and Dropbox are listed as "Soon".
  - Paste a screenshot anywhere on the page with Ctrl V or ⌘ V.
  - Drop an image anywhere on the page; a full-page overlay shows where it will go. Images dragged in from another browser tab work too.
  - Paste or type a link to an image. If the link is a web page, ChartHawk uses the page's preview image, which is usually the chart. The new `/fetch_image` route downloads it on the server and blocks private network addresses.
- **Model picker grouped by company** (Anthropic, OpenAI, Google, xAI), shown on the landing page and above the chat box. Signed-out visitors see a "Sign in" lock on every model except the default. Choosing a locked model opens sign-in and keeps you on the page, and that model is selected once you're signed in. Search and company filters turn on automatically when there are more than 6 models.

### Changed
- Privacy policy updated: it names all four AI companies (Anthropic, OpenAI, Google, xAI) and says a chart goes only to the one whose model you choose. It also covers links, Google sign-in, Railway hosting, PostHog analytics and public sharing.
- Model names on answers now show the model ("Claude Sonnet 4.6", "GPT-4.1") instead of the company ("Claude (Anthropic)").
- In the chat view, the profile strip and "API Keys" in the sidebar now open the dashboard's Profile and API keys pages instead of pop-ups, so each is edited in one place. The old profile and API-key pop-ups were removed.

### Fixed
- The sidebar no longer shows a broken image when an account has no profile photo.

## 2026-10-28

### Added
- **Signed-in dashboard (`/dashboard`)** — a separate home page after login, modeled on retailer account pages: greeting card with member-since date and stats, side navigation, recent analyses, a searchable/filterable list of all your charts and analyses (star, copy share link), profile editing, API key management, and an Admin dashboard link for admins.

### Changed
- Signing in from the landing page (email or Google) now goes to `/dashboard` instead of flipping the landing page into the chat view. Signed-in visitors to `/` stay on the landing page, which shows "My dashboard" in the header.
- "Open analysis" links use `/?chart=<id>`, which opens that chart directly with no landing-page flash; the address bar tracks the chart you're viewing.
- Replaced "audit" with "analyze"/"analysis" across the app (landing, chat, gallery, share pages, and metadata).

## 2026-07-16

### Added
- **Multi-model AI support** — analyze charts with Claude, GPT-4.1, Gemini, or Grok. A model selector next to the chat input remembers your last choice (defaults to Claude for new users). Only providers with a configured API key show up in the dropdown.

### Fixed
- Anonymous (signed-out) requests always use the default provider now, so unauthenticated traffic can't be used to spend non-default provider API keys — model selection requires signing in.
- The History sidebar no longer shows other users' public charts mixed in with your own; the public Gallery page is unaffected.
