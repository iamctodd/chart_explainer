---
name: charthawk
description: Analyze a chart or data visualization image to extract key insights, identify trends and anomalies, flag common misinterpretations, and suggest improvements. Use when a user uploads a chart image or asks for help understanding a graph or visualization.
---

# ChartHawk

## When to use
- User uploads a chart, graph, or data visualization image
- User asks "what does this chart mean?" or "help me understand this graph"
- User wants to know if their chart is clear and easy to read
- User is creating a visualization and wants feedback

## How to use

### Step 1 — Upload the image
Accept any image format (PNG, JPG, GIF, PDF). The file size limit is 5MB.

### Step 2 — Call the ChartHawk API
```bash
curl -X POST https://charthawk.info/analyze \
  -H "Authorization: Bearer $CHARTHAWK_API_KEY" \
  -F "chart=@/path/to/image.png"
