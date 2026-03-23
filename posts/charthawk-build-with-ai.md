# I Built a Chart Analysis App with AI — Here's What Actually Happened

*Build with AI, Vol. 4*

---

We've all been in that meeting.

Someone puts up a dense chart — a funnel analysis, a cohort retention grid, a multi-axis revenue breakdown — and everyone nods like they get it. Nobody wants to be the one who asks. So the meeting moves on, the slide gets exported to a deck, and three weeks later someone makes a product decision based on a chart they never fully understood.

That moment is what ChartHawk is for.

**[ChartHawk](https://charthawk.info)** is a web app that lets you upload any chart image and get a structured plain-English explanation back in seconds. What it shows. What it doesn't show. The key insights. The misinterpretations people usually make. You can ask follow-up questions, save your history, and export the analysis. It's powered by Claude, Anthropic's AI model, which turns out to be exceptionally good at reading and reasoning about visual data.

This is the story of how I built it — what went smoothly, what broke badly, and what building with AI as a coding partner actually feels like when you're past the demo phase and in the weeds of real product development.

---

## The Stack — Every Choice Was Deliberate

Before the first line of code, I spent about 20 minutes deciding what *not* to use.

No React. No Next.js. No TypeScript compilation step. No ORM. The goal was a product I could ship, iterate on, and debug quickly — not a showcase for modern frontend infrastructure.

Here's what I landed on and why:

**Flask (Python)** — A thin, readable web framework with no magic. For this app, the backend is essentially a proxy: receive an image, forward it to Claude's API, stream the response back to the browser. Flask is 50 lines for that. A heavier framework would've been 150 lines with three config files.

**Vanilla JavaScript** — No build toolchain, no bundler, no `node_modules` folder eating my disk. The entire frontend is one HTML file. This sounds insane until you realize how fast it is to find a bug, fix it, and reload the page.

**Claude `claude-sonnet-4-20250514`** — Anthropic's vision-capable model. It receives the chart image as a base64-encoded payload and returns structured markdown analysis. The model is genuinely excellent at this — it identifies axis labels, trend directions, statistical patterns, and common misreadings without you having to ask for any of that specifically. The prompt does a lot of work here (more on that in a moment).

**Server-Sent Events (SSE) for streaming** — Instead of waiting for the full analysis to generate and then displaying it all at once, SSE lets the response stream token-by-token directly to the browser. The chart appears immediately, then words start flowing. This one UX change made the app feel dramatically more alive.

**Supabase** — Auth plus a Postgres database in one platform, with a free tier that covers everything at early scale. The killer feature is **Row Level Security (RLS)** — a Postgres feature where you write SQL policies that control who can see what data. Four lines of SQL and every user's chart history is automatically isolated. No `WHERE user_id = ?` clauses scattered through the Python code.

**Railway** — One-click deploys connected to GitHub, environment variable management, automatic HTTPS. Zero infrastructure overhead. The app has been running for months without me thinking about servers.

**PostHog** (analytics) and **Formspree** (feedback form) — Both have generous free tiers and take about 15 minutes each to integrate. PostHog tracks which features get used; Formspree catches feedback without me running a backend email server.

---

## Phase 1: MVP — Get Something Working

The first version did one thing: accept a chart image, send it to Claude, and show the analysis.

### The Prompt Is the Product

I spent more time on the analysis prompt than on any other single piece of code. Claude is capable enough that it'll write something reasonable even with a vague prompt — but "something reasonable" isn't a product. A product has a consistent, predictable structure that users can learn to rely on.

Here's the shape of what I landed on (simplified):

```
Analyze this chart and structure your response in exactly four sections:

## What It Shows
Describe what data is being represented and the main trend or pattern.

## Key Insights
2–4 specific, concrete observations worth noting.

## What It Doesn't Show
Limitations, missing context, or what the chart can't tell you.

## Common Misinterpretations
How people often misread this type of chart or this specific data.
```

That four-part structure became the backbone of the product. Every analysis users receive follows the same shape, which means they know exactly where to look for what they need.

### Streaming Makes It Feel Fast

The technical implementation of SSE is simpler than it sounds. The Flask endpoint uses Anthropic's streaming API, wraps each text chunk in an SSE-formatted string, and flushes it to the browser:

```python
def stream_text(stream):
    with stream as s:
        for text in s.text_stream:
            yield f"data: {json.dumps({'type': 'text', 'content': text})}\n\n"
    yield f"data: {json.dumps({'type': 'done'})}\n\n"
```

One trick worth calling out: I fire an `image` event *before* the first text chunk, so the chart thumbnail renders in the UI immediately. Users see their chart appear in about 200ms, then the analysis starts streaming in. That sequencing matters a lot for perceived performance.

### The UI Redesign

The first version had analysis cards stacked vertically in a box. It worked, but it felt like a report viewer, not a tool.

I redesigned it to look like a modern LLM chat interface — the kind of layout you'd recognize from Claude.ai or Perplexity. A left sidebar shows your chart history. Clicking a chart loads the analysis and conversation in the main panel. A persistent input bar at the bottom handles follow-up questions.

That layout change reframed the product from "chart explainer" to "chart analyst you can talk to." Small shift in interface, big shift in how it feels to use.

---

## Phase 2: Follow-Up Conversations

The first version was one-shot. You got the analysis. That was it.

The obvious next step: what if you could ask follow-up questions? "What does the spike in March mean?" "Is this a statistically significant trend?" "What additional data would I need to draw a stronger conclusion?"

Adding that required a `/followup_stream` endpoint that accepts the current chart image *plus* the full conversation history. Claude needs both to answer follow-up questions intelligently.

There was one subtle bug here that took a while to spot. When I sent the follow-up request, Claude kept re-summarizing the chart in its response — as if it had never seen the original analysis. The fix: before sending the conversation history, I inject the original analysis as a *synthetic assistant turn*. Claude sees its own earlier response, which prevents it from re-explaining everything from scratch.

```python
conversation_history = [
    {"role": "assistant", "content": analysis_raw},  # synthetic turn
    *actual_conversation_messages
]
```

That one-liner made follow-up conversations feel completely natural.

---

## Phase 3: Auth and the Database — Where Things Got Interesting

This is where the build got humbling.

### Why Bother With Auth At All?

The MVP had no accounts. Chart history lived in the browser's memory. Reload the page, lose everything. That's fine for a demo; it's not fine for a product people return to.

Adding Supabase meant users could sign in with Google or email and have their history persist across devices. It also meant I needed to think seriously about data isolation — making sure User A can never see User B's charts.

This is where **Row Level Security** (RLS) earned its reputation. Two SQL statements and the database enforces isolation automatically:

```sql
-- Users can only read their own charts
create policy "Users can view their own charts" on public.charts
  for select using (auth.uid() = user_id);

-- Users can only read messages belonging to their charts
create policy "Users can view messages for their charts" on public.messages
  for select using (
    chart_id in (select id from public.charts where user_id = auth.uid())
  );
```

That's it. No filtering logic in Python. No risk of accidentally forgetting a `WHERE` clause and leaking data. The database just handles it.

### Three Authentication Bugs in a Row

Getting auth working was a multi-step process of things that looked like they were working but weren't.

**Bug 1 — Error 400: redirect_uri_mismatch.** Google OAuth rejected the sign-in callback because the Supabase callback URL wasn't listed as an authorized redirect URI in Google Cloud Console. Easy fix once you know where to look: add `https://your-project.supabase.co/auth/v1/callback` to the list. The error message was specific enough that this one was fast.

**Bug 2 — Wrong API key format.** Supabase recently introduced a new `sb_publishable_` key format for newer projects. The version of `@supabase/supabase-js` I was using expected the old JWT-format key (`eyJhbGci...`). Using the new format caused silent authentication failures — no error in the console, just auth quietly not working. Switching to the JWT key fixed it immediately.

**Bug 3 — PKCE flow silently failing.** By default, the Supabase JS client uses PKCE (Proof Key for Code Exchange), which is the more secure OAuth flow for SPAs. In theory. In practice, the code exchange step was failing silently after the Google OAuth redirect — the page just reloaded with no sign-in state. Switching to `flowType: 'implicit'` fixed it:

```javascript
supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
    auth: { flowType: 'implicit' }
})
```

Implicit flow is technically less secure than PKCE, but a flow that works is infinitely more secure than a flow that fails silently.

### The Hardest Bug: The Web Lock

This one took a full afternoon.

After getting auth working, I added a "View my history" button on the landing screen. Users could click it and load their previous charts. Simple enough. Except when I tested it, nothing happened. No error in the console. No spinner. Nothing.

I added debug logging and traced the execution. The function was running. It was reaching the Supabase query. Then it just... stopped. No error. No response. Indefinitely.

After a lot of console.log statements and frustration, I found this buried in the browser's error output:

```
Lock 'lock:sb-csjiymeycevxqmlmqcwc-auth-token' was released because another request stole it
```

Supabase JS acquires a browser Web Lock during its initialization to safely manage the auth token across tabs. If that lock gets stolen — by another tab, by a rapid page refresh, by anything — every subsequent `supabase.from()` call hangs indefinitely waiting for the lock to become available again. No timeout. No error thrown. Just silence.

The fix was to bypass the Supabase client entirely for `loadHistory()`. Instead of using the JS library, I read the access token directly from `localStorage` and made plain `fetch()` calls to Supabase's REST API:

```javascript
async function loadHistory() {
    // Read the token directly — bypasses the Web Lock entirely
    const projectRef = SUPABASE_URL.split('//')[1].split('.')[0];
    const stored = localStorage.getItem(`sb-${projectRef}-auth-token`);
    const accessToken = JSON.parse(stored)?.access_token;

    const headers = {
        'Authorization': `Bearer ${accessToken}`,
        'apikey': SUPABASE_ANON_KEY,
    };

    const res = await fetch(`${SUPABASE_URL}/rest/v1/charts?select=*&order=created_at.desc`, { headers });
    // ...
}
```

Instantly responsive. The Web Lock is still acquired during initialization — I'm just not waiting for it to be released before fetching data.

---

## Phase 4: The Admin Dashboard

Before I thought about charging anyone for ChartHawk, I needed to see what it actually cost to run.

I built a separate admin dashboard at `/admin` — a standalone HTML page that shows real usage data from a `usage` table in the database. Every analysis and follow-up gets logged with its token counts. The dashboard calculates cost in real-time using Claude's pricing ($3 per million input tokens, $15 per million output tokens for Sonnet 4).

Seeing `$0.006` per chart analysis in the dashboard on day one was clarifying. That number shapes every subsequent decision about pricing, free tiers, and what to optimize.

The dashboard also handles admin promotion/demotion. When another user needs admin access, I enter their email into a form and the app calls Supabase's admin API to set `is_admin: true` in their user metadata. A `require_admin` decorator on every admin route checks that flag on every request.

---

## Phase 5: The Polish Layer

The last phase was a series of smaller features that individually feel minor but collectively determine whether a product feels finished or half-done.

**User profiles** — users can set a display name, upload an avatar (resized to 64×64 via an HTML canvas before being stored as base64 in Supabase user metadata), and change their password. Email users can change passwords via a re-authentication flow. Google OAuth users get a friendly message explaining that their password is managed by Google.

**Collapsible sidebar** — a chevron button on desktop collapses the sidebar to give more room for the analysis. On mobile, the sidebar becomes a full-screen drawer triggered by a hamburger button.

**Export to Markdown** — download any analysis plus its conversation thread as a `.md` file. This is entirely client-side: no backend involved, no API call. Just a `Blob`, a `URL.createObjectURL`, and a synthetic `<a>` click:

```javascript
const blob = new Blob([markdownContent], { type: 'text/markdown' });
const url = URL.createObjectURL(blob);
const a = Object.assign(document.createElement('a'), {
    href: url,
    download: `${chartName}.md`
});
a.click();
URL.revokeObjectURL(url);
```

**PostHog analytics** — six events: `user_signed_in`, `tos_accepted`, `chart_analyzed`, `followup_asked`, `chart_exported`, `signed_out`. The `posthog_key` is injected from a Railway environment variable at render time, so if the key isn't set, the entire analytics block is skipped and there are zero errors.

### The Modal Bug That Shouldn't Have Taken as Long as It Did

Late in the build, several "Got it" buttons on informational modals (Pricing, API Docs, How It Works) stopped working. They were visually present. They looked clickable. They did nothing.

I traced the event listeners, checked for typos in element IDs, looked for JavaScript errors. Nothing. Eventually I found the problem: the modal HTML was placed *after* the closing `</script>` tag. The `addEventListener` calls were executing during page load, at which point those DOM elements didn't exist yet — `getElementById` returned null, and the listeners were silently attached to nothing.

Moving the modal HTML to before the `</script>` tag fixed all of them instantly. Obvious in retrospect. Annoying to track down.

---

## Five Things I Actually Learned

### 1. AI writes 90% of the code, but you debug 100% of the bugs.

Claude (the AI, not the app) wrote the majority of ChartHawk's code. It handled boilerplate, suggested patterns, translated requirements into working implementations. What it couldn't do: observe what was actually happening in a live browser session at 2pm on a Tuesday when the Web Lock was stolen by a tab I'd closed three hours earlier. Debugging still requires a human with context.

### 2. The simplest auth flow that works beats the most secure flow that doesn't.

PKCE is recommended for good reasons. But "recommended" assumes it actually runs to completion. Implicit flow has known theoretical weaknesses; PKCE failing silently has practical ones. Ship the thing that works, document the tradeoffs, harden later.

### 3. Row Level Security is the most underrated database feature.

Four lines of SQL replaced an entire authorization layer. I didn't have to write a single `WHERE user_id = ?` clause in Python. I didn't have to worry about accidentally omitting one. The database just doesn't return data that the current user isn't allowed to see. If you're using Postgres, you should be using RLS.

### 4. Build the admin dashboard before you think you need it.

I almost skipped it. "I'll add usage tracking later when there are real users." I'm glad I didn't. Seeing actual numbers — cost per analysis, which users are most active, which features get used — immediately changed how I thought about every subsequent product decision. The dashboard is just an HTML file and a few SQL queries. It's not much work for a lot of clarity.

### 5. The AI-assisted workflow compounds over time.

The first features took days. By the end, features like Export (the button, the JavaScript, the CSS styling) took about 15 minutes. Not because I was moving faster or cutting corners — because the codebase patterns were established, Claude understood the context deeply, and we weren't starting from scratch on anything. The productivity gains from AI assistance get *larger* as a project matures, not smaller.

---

## What's Next

ChartHawk is live at **[charthawk.info](https://charthawk.info)** and free to try.

A few things I'm working on:

- **PDF support** — upload a multi-page report and analyze individual charts within it
- **Shareable links** — send an analysis to a colleague without requiring them to sign in
- **API access** — for teams that want to integrate chart analysis into existing workflows

If you try it, I'd genuinely love to know what you think. The feedback button in the app goes directly to my inbox.

And if you're building something similar — a thin Flask/Claude proxy for a specific domain problem — I hope the bugs documented here save you an afternoon. The Web Lock one especially.

---

*ChartHawk is open source on [GitHub](https://github.com/iamctodd/charthawk). Built with [Anthropic Claude](https://anthropic.com/claude), deployed on [Railway](https://railway.app).*
