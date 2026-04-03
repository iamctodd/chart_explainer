# 🗺️ ChartHawk Roadmap

*Last updated: April 2, 2026*

---

## ✅ Shipped

- [x] Chart upload and AI-powered analysis (Claude claude-sonnet-4-20250514 with vision)
- [x] Real-time streaming responses (SSE)
- [x] Follow-up conversation threads per chart
- [x] Multi-chart session history with sidebar
- [x] Google OAuth + email/password auth (Supabase)
- [x] Persistent chart + conversation history (Postgres + RLS)
- [x] User profiles (name, avatar, password change)
- [x] Export analysis to Markdown
- [x] Public Gallery (community chart feed)
- [x] Shareable analysis links (`/share/<id>`)
- [x] Per-chart public/private toggle
- [x] Comment threads on public charts
- [x] Admin dashboard (usage, cost, promote/demote)
- [x] API key system (`sk-hawk-...`) for programmatic access
- [x] `/api/v1/analyze` endpoint (JSON, no SSE — for scripts and skills)
- [x] Claude Code Skill (`skills/charthawk.md`)
- [x] PostHog analytics
- [x] Formspree feedback integration
- [x] Railway deployment (gunicorn, auto-deploy from GitHub)
- [x] 5MB upload size limit (client + server enforced)

---

## 🔜 Next Up

### ALT text generation
Auto-generate a concise, screen-reader-friendly alt text description for every uploaded chart. Stored alongside the analysis. Used in:
- Gallery card `<img alt="...">` attributes
- Share page image rendering
- Exported Markdown files

*Implementation: small addition to the analysis prompt; new `alt_text` column on `charts` table.*

### Chart type tagging
Ask Claude to classify each chart at analysis time (bar, line, scatter, heatmap, pie, funnel, treemap, etc.) and store it as a structured tag. Enables:
- Filter the public gallery by chart type
- Tag badges on gallery cards and share pages
- Search/filter within a user's own history

*Implementation: add to `gallery_summary` JSON or a dedicated `chart_type` column; filter UI on gallery page.*

### UX + UI polish pass
Inspired by [ini.fyi](https://ini.fyi) — richer micro-interactions, smoother transitions, more considered hover/focus states. Particularly relevant for:
- Gallery card hover animations
- Share page scroll behavior
- Analysis reveal transitions

---

## 🔮 Future Considerations

### Analysis enhancements
- [ ] Suggest alternative visualizations for the same data
- [ ] Side-by-side chart comparison
- [ ] Data extraction (pull numbers out of a chart image)
- [ ] Industry-specific insight modes (finance, product, marketing)

### File type expansion
- [ ] PDF upload — extract and analyze individual charts from multi-page documents
- [ ] Batch upload — analyze multiple charts in one session

### Sharing + collaboration
- [ ] Shareable collections (group related charts)
- [ ] Team workspaces with shared history
- [ ] Email sharing of analysis links

### Integrations
- [ ] Browser extension — analyze any chart on any webpage
- [ ] Slack app — forward a chart image, get analysis in thread
- [ ] Google Slides / PowerPoint — analyze charts directly in presentations

### API + developer experience
- [ ] OpenAPI spec / Swagger docs for `/api/v1/`
- [ ] Webhook support (POST analysis results to a URL)
- [ ] MCP server (`charthawk-mcp`) for broader Claude ecosystem compatibility

---

## 💡 Ideas Under Consideration

- **AI tutor mode** — teach users how to read a specific chart type better
- **Accessibility checker** — flag charts that are hard to read (color contrast, missing labels, etc.)
- **Chart creation wizard** — help users build better visualizations from scratch
- **Video support** — extract and analyze charts from presentation recordings

### 📱 Mobile App
Snap a photo of a chart (whiteboard, printed report, screen) or choose from your camera roll and get an analysis instantly. The mobile web experience already works reasonably well, but a native app unlocks meaningful advantages:

- **Camera integration** — direct viewfinder capture, not just photo library picker
- **Push notifications** — get notified when a long analysis completes
- **Home screen shortcut** — one tap to open and shoot, no browser navigation
- **Offline history** — browse past analyses without a connection
- **Share sheet integration** — share a chart image from any app directly to ChartHawk for analysis
- **Widgets** — quick-glance summary of your most recent analysis

*Likely approach: React Native or a PWA with camera API — the `/api/v1/analyze` endpoint is already mobile-ready.*

---

## 📊 Success Metrics

- **Adoption**: 100 unique signed-in users
- **Engagement**: 3+ charts analyzed per session
- **Retention**: 20% weekly active users
- **Quality**: <5% of sessions trigger an error
- **Performance**: <3s to first analysis token

---

## Release History

- **v0.1** — ✅ January 2026 — MVP (upload, analyze, streaming)
- **v0.2** — ✅ March 2026 — Auth, history, admin, export, analytics
- **v0.3** — ✅ April 2026 — Gallery, sharing, comments, API keys, Claude Skill
- **v0.4** — 🔜 ALT text, chart type tagging, UI polish
