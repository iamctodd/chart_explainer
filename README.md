# ChartHawk

**See what the data's hiding.**

ChartHawk analyzes a chart image and explains, in plain English:
- what it shows
- what it's really saying
- what it doesn't show
- how people often misread it

It also points out truncated axes, cherry-picked ranges and misleading chart types, and can redraw the chart with those problems fixed.

🔗 **Live:** [charthawk.info](https://charthawk.info)

---

## Features

**Analyzing a chart**
- **A chat-style composer.** Upload a chart, paste a screenshot (Ctrl V / ⌘ V), drop an image anywhere on the page, or paste a link to an image or to a page that contains a chart. You can add a question, and it's asked once the analysis is ready.
- **Choice of AI model.** Claude, GPT, Gemini and Grok, grouped by company in a picker. Each answer is labelled with the model that wrote it, and you can switch models partway through a chat. Signed-out visitors use the default model.
- **Streaming analysis** in five parts: what this shows, what it's really saying, what it does NOT show, common misreadings, and what could be improved.
- **Follow-up questions** about the same chart.
- **"Show me an improved version."** The model redraws the chart as an SVG with its suggested fixes applied and shows it next to the original.

**Accounts and sharing**
- Email or Google sign-in (Supabase), with chart and conversation history saved per user.
- A dashboard at `/dashboard` with your charts and analyses, your profile and your API keys.
- Public gallery (`/gallery`), share links (`/share/<id>`) and comments on public charts.
- Export any analysis to Markdown.

**For developers and admins**
- REST endpoint `POST /api/v1/analyze`, which takes `sk-hawk-…` API keys you create in the dashboard.
- A Claude Code skill that calls that endpoint. See [skills/README.md](skills/README.md).
- An admin dashboard (`/admin`) with usage, cost, and promote/demote controls for users.

---

## Tech stack

| Part | What it uses |
|---|---|
| Backend | Python, Flask, gunicorn |
| Frontend | Plain HTML, CSS and JavaScript (`web_app/templates/`) |
| AI models | Anthropic, OpenAI, Google Gemini and xAI, routed through `providers.py` |
| Auth and database | Supabase (Postgres with row-level security) |
| Analytics | PostHog |
| Feedback form | Formspree |
| Hosting | Railway |

---

## Running it locally

**Requirements:** Python 3.9+ and at least an Anthropic API key ([console.anthropic.com](https://console.anthropic.com)).

```bash
git clone https://github.com/iamctodd/chart_explainer.git
cd chart_explainer/web_app
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Set your environment variables:

```bash
export ANTHROPIC_API_KEY="..."          # required: the default model

# Optional: each key you set adds that company's model to the picker
export OPENAI_API_KEY="..."
export GOOGLE_API_KEY="..."
export XAI_API_KEY="..."

# Optional: point at your own Supabase project (defaults to ChartHawk's)
export SUPABASE_URL="..."
export SUPABASE_ANON_KEY="..."
export SUPABASE_SERVICE_KEY="..."       # service_role key, needed for the admin page, usage tracking and publishing

export POSTHOG_KEY="..."                # optional analytics
export PORT=5001                        # optional, defaults to 5000
```

Then start it and open `http://localhost:5001`:

```bash
python3 app.py
```

### Adding or changing models

Models are listed in `PROVIDERS` in `web_app/providers.py`. Each entry has:
- the API model ID
- the display name (`label`)
- the `company` it's grouped under in the picker
- price per million tokens (used for the admin dashboard's cost figures)
- optional `tags` such as `fast` or `new`

A model only appears in the picker when its API key is set. Any OpenAI-compatible provider needs only a registry entry and a `base_url`, with no new code.

---

## Deploying on Railway

1. Connect this GitHub repository to a Railway project.
2. Set the root directory to `web_app`.
3. Add the environment variables above. `ANTHROPIC_API_KEY` and `SUPABASE_SERVICE_KEY` are the important ones.
4. Deploy. `railway.json` starts the app with `gunicorn app:app --timeout 180`.

Railway redeploys automatically when `main` changes.

---

## Project structure

```
chart_explainer/
├── web_app/
│   ├── app.py               # Flask routes: analysis, follow-ups, gallery, admin, API keys
│   ├── providers.py         # Model registry and adapters for each AI company
│   ├── image_fetch.py       # Downloads images from pasted links (blocks private networks)
│   ├── templates/
│   │   ├── index.html       # Landing page composer and chat view
│   │   ├── dashboard.html   # Signed-in dashboard
│   │   ├── gallery.html     # Public gallery
│   │   ├── share.html       # Shared analysis page
│   │   └── admin.html       # Admin dashboard
│   ├── requirements.txt
│   └── railway.json
├── skills/                  # Claude Code skill for the ChartHawk API
├── slack_app/               # Slack bot (experimental)
├── tasks/                   # Supabase SQL migrations
├── example_charts/          # Sample charts for testing
├── documents/               # Brand style guide and product docs
├── CHANGELOG.md
└── ROADMAP.md
```

---

## API

```bash
curl -X POST https://charthawk.info/api/v1/analyze \
  -H "Authorization: Bearer sk-hawk-..." \
  -F "chart=@my-chart.png"
```

Create an API key in your dashboard under **API keys**.

---

## Roadmap and changes

- [ROADMAP.md](ROADMAP.md) lists planned features.
- [CHANGELOG.md](CHANGELOG.md) lists what changed and when.

## Contributing

Pull requests are welcome. Create a branch, make your change, and open a PR against `main`.

## Feedback

Use **Send feedback** in the app, or [open an issue](https://github.com/iamctodd/chart_explainer/issues).

## License

MIT. See [LICENSE](LICENSE).

---

Made by [@iamctodd](https://github.com/iamctodd). Built in public.
