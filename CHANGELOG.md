# Changelog

All notable changes to ChartHawk are documented here.

## 2026-07-16

### Added
- **Multi-model AI support** — analyze charts with Claude, GPT-4.1, Gemini, or Grok. A model selector next to the chat input remembers your last choice (defaults to Claude for new users). Only providers with a configured API key show up in the dropdown.

### Fixed
- Anonymous (signed-out) requests always use the default provider now, so unauthenticated traffic can't be used to spend non-default provider API keys — model selection requires signing in.
- The History sidebar no longer shows other users' public charts mixed in with your own; the public Gallery page is unaffected.
