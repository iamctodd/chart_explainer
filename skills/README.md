# ChartHawk — Claude Code Skill

A Claude Code skill that analyzes chart and data visualization images using the [ChartHawk](https://charthawk.info) API. Drop in any chart and get an instant structured breakdown: what it shows, key insights, what it doesn't show, common misinterpretations, and improvement suggestions.

## What it does

When you upload a chart image and ask Claude to analyze it, this skill automatically calls the ChartHawk API and returns a structured analysis covering:

- **What it shows** — what data is being presented and how
- **Key insights** — the main takeaways and patterns
- **What it doesn't show** — limitations and missing context
- **Common misinterpretations** — how people typically misread this chart type
- **Improvements** — suggestions to make the chart clearer

Supports bar, line, scatter, heatmap, pie, histogram, and any other chart image format.

## Prerequisites

1. A [ChartHawk account](https://charthawk.info) (free to sign up)
2. A ChartHawk API key — generate one from the **🔑 API Keys** section in the sidebar after signing in

## Installation

### 1. Copy the skill file

Place `charthawk.md` in your project's skills directory:

```bash
# For a specific project
cp charthawk.md /your/project/.claude/skills/charthawk.md

# Or clone this repo and use it directly
```

### 2. Set your API key

Add your ChartHawk API key to `~/.claude/settings.local.json` (global, works in all projects):

```json
{
  "env": {
    "CHARTHAWK_API_KEY": "sk-hawk-..."
  }
}
```

Or add it to `.claude/settings.local.json` inside a specific project to scope it there.

> **Note:** Use `settings.local.json`, not `settings.json`. The local file is excluded from git and should never be committed.

## Usage

Open Claude Code in any project, upload a chart image, and ask:

```
analyze this chart
```

or

```
what does this chart show?
help me understand this graph
is this visualization clear?
```

Claude will automatically invoke the ChartHawk skill and return a structured analysis.

## Direct API usage

You can also call the ChartHawk API directly from any script:

```bash
curl -X POST https://charthawk.info/api/v1/analyze \
  -H "Authorization: Bearer $CHARTHAWK_API_KEY" \
  -F "chart=@/path/to/chart.png"
```

**Response:**
```json
{
  "analysis": "## What this shows\n...",
  "filename": "chart.png"
}
```

### File requirements
| Property | Value |
|---|---|
| Formats | PNG, JPG, GIF, WEBP |
| Max size | 5MB |
| Auth header | `Bearer sk-hawk-...` |

## Troubleshooting

**401 Unauthorized** — Your API key is invalid or revoked. Generate a new one from [charthawk.info](https://charthawk.info) → Sign in → 🔑 API Keys.

**413 Request Entity Too Large** — Image exceeds 5MB. Resize or compress the image before uploading.

**Skill not triggering** — Make sure `charthawk.md` is in the correct `.claude/skills/` directory and that `CHARTHAWK_API_KEY` is set in your `settings.local.json`.

## Links

- [ChartHawk](https://charthawk.info) — the app
- [Public Gallery](https://charthawk.info/gallery) — community chart analyses
- [ChartHawk on GitHub](https://github.com/iamctodd/chart_explainer)
