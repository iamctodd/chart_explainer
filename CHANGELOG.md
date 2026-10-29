# Changelog

All notable changes to ChartHawk are documented here.

## 2026-10-29

### Changed
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
