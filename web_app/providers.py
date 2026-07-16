"""Multi-provider AI routing for ChartHawk's chart-analysis chat.

Each provider adapter takes a provider-agnostic list of `turns` and streams
back plain text chunks, so app.py's routes stay identical regardless of
which backend answered.
"""
import base64
import os
import threading
import anthropic
from openai import OpenAI, BadRequestError
from google import genai
from google.genai import types as genai_types

# ── Registry ───────────────────────────────────────────────────────────────────
# Pricing is USD per 1M tokens, current as of implementation time — check each
# provider's pricing page if costs in the admin dashboard look off.
# 'kind' selects which adapter family handles the provider; 'openai_compatible'
# providers only need a registry entry (+ optional base_url) to be added, no new code.

PROVIDERS = {
    'anthropic': {
        'label':   'Claude (Anthropic)',
        'env_key': 'ANTHROPIC_API_KEY',
        'model':   'claude-sonnet-4-6',
        'pricing': {'input': 3.0, 'output': 15.0},
        'kind':    'anthropic',
    },
    'openai': {
        'label':   'GPT-4.1 (OpenAI)',
        'env_key': 'OPENAI_API_KEY',
        'model':   'gpt-4.1',
        'pricing': {'input': 2.0, 'output': 8.0},
        'kind':    'openai_compatible',
    },
    'gemini': {
        'label':   'Gemini (Google)',
        'env_key': 'GOOGLE_API_KEY',
        'model':   'gemini-3-flash-preview',
        'pricing': {'input': 0.5, 'output': 3.0},
        'kind':    'gemini',
    },
    'xai': {
        'label':    'Grok (xAI)',
        'env_key':  'XAI_API_KEY',
        'model':    'grok-4.5',
        'pricing':  {'input': 2.0, 'output': 6.0},
        'kind':     'openai_compatible',
        'base_url': 'https://api.x.ai/v1',
    },
}

DEFAULT_PROVIDER = 'anthropic'

ANALYSIS_PROMPT = """Analyze this chart/graph and provide:

1. **What this shows**: Explain what data is being presented (2-3 sentences)
2. **What this chart is really saying**: What are the main takeaways or patterns?
3. **What this does NOT show**: Important limitations or what's missing
4. **What people often misread here**: Common ways people might misread this
5. **What could be improved**: How to make this chart easier to understand

Be clear and helpful, not condescending. If the axes are misleading or there are visual tricks, point them out."""


def available_providers():
    """Providers whose API key is actually configured — the only ones the UI should offer."""
    return [
        {'id': pid, 'label': cfg['label']}
        for pid, cfg in PROVIDERS.items()
        if os.environ.get(cfg['env_key'])
    ]


def resolve_provider(value):
    """Validate a requested provider id. Raises ValueError with a user-facing message if unusable."""
    pid = value or DEFAULT_PROVIDER
    cfg = PROVIDERS.get(pid)
    if not cfg or not os.environ.get(cfg['env_key']):
        raise ValueError('This model isn\'t configured on the server.')
    return pid


def calculate_cost(provider_id, input_tokens, output_tokens):
    """Cost in USD for a call, using the given provider's per-token pricing."""
    pricing = PROVIDERS[provider_id]['pricing']
    return round((input_tokens * pricing['input'] + output_tokens * pricing['output']) / 1_000_000, 6)


# ── Turn building ──────────────────────────────────────────────────────────────

def build_turns(image_base64, media_type, analysis_raw, conversation_history, question):
    """Provider-agnostic conversation turns. Only the first turn ever carries an image."""
    turns = [{'role': 'user', 'text': ANALYSIS_PROMPT, 'image_b64': image_base64, 'image_media_type': media_type}]
    if analysis_raw:
        turns.append({'role': 'assistant', 'text': analysis_raw})
    for turn in conversation_history:
        turns.append({'role': turn['role'], 'text': turn['content']})
    if question:
        turns.append({'role': 'user', 'text': question})
    return turns


def _build_anthropic_messages(turns):
    messages = []
    for t in turns:
        if t.get('image_b64'):
            content = [
                {'type': 'image', 'source': {'type': 'base64', 'media_type': t['image_media_type'], 'data': t['image_b64']}},
                {'type': 'text', 'text': t['text']},
            ]
        else:
            content = t['text']
        messages.append({'role': t['role'], 'content': content})
    return messages


def _build_openai_messages(turns):
    messages = []
    for t in turns:
        if t.get('image_b64'):
            data_url = f"data:{t['image_media_type']};base64,{t['image_b64']}"
            content = [
                {'type': 'image_url', 'image_url': {'url': data_url}},
                {'type': 'text', 'text': t['text']},
            ]
        else:
            content = t['text']
        messages.append({'role': t['role'], 'content': content})
    return messages


def _build_gemini_contents(turns):
    contents = []
    for t in turns:
        parts = []
        if t.get('image_b64'):
            parts.append(genai_types.Part.from_bytes(
                data=base64.b64decode(t['image_b64']), mime_type=t['image_media_type'],
            ))
        parts.append(genai_types.Part.from_text(text=t['text']))
        role = 'model' if t['role'] == 'assistant' else 'user'
        contents.append(genai_types.Content(role=role, parts=parts))
    return contents


def _gemini_config(max_tokens):
    # Gemini 3's "thinking" tokens are drawn from the same max_output_tokens budget
    # as the visible answer — for a direct chart description we don't need deep
    # reasoning, so disable it to keep the full budget for the actual response.
    return genai_types.GenerateContentConfig(
        max_output_tokens=max_tokens,
        thinking_config=genai_types.ThinkingConfig(thinking_budget=0),
    )


# ── Lazily-constructed clients ─────────────────────────────────────────────────

_clients = {}
_clients_lock = threading.Lock()


def _anthropic_client():
    if 'anthropic' not in _clients:
        with _clients_lock:
            if 'anthropic' not in _clients:
                _clients['anthropic'] = anthropic.Anthropic(api_key=os.environ.get('ANTHROPIC_API_KEY'))
    return _clients['anthropic']


def _openai_compatible_client(provider_id, base_url=None):
    if provider_id not in _clients:
        with _clients_lock:
            if provider_id not in _clients:
                _clients[provider_id] = OpenAI(api_key=os.environ.get(PROVIDERS[provider_id]['env_key']), base_url=base_url)
    return _clients[provider_id]


def _gemini_client():
    if 'gemini' not in _clients:
        with _clients_lock:
            if 'gemini' not in _clients:
                _clients['gemini'] = genai.Client(api_key=os.environ.get('GOOGLE_API_KEY'))
    return _clients['gemini']


# ── Streaming adapters ──────────────────────────────────────────────────────────
# Each yields ('text', chunk) repeatedly, then ('usage', {'input_tokens', 'output_tokens'}) once.

def _stream_anthropic(turns, max_tokens):
    messages = _build_anthropic_messages(turns)
    with _anthropic_client().messages.stream(
        model=PROVIDERS['anthropic']['model'], max_tokens=max_tokens, messages=messages,
    ) as stream:
        for chunk in stream.text_stream:
            yield ('text', chunk)
        # A failure capturing usage must not turn an already-fully-streamed answer into
        # an error for the client — degrade to zero usage instead of raising.
        try:
            usage = stream.get_final_message().usage
            yield ('usage', {'input_tokens': usage.input_tokens, 'output_tokens': usage.output_tokens})
        except Exception as e:
            print(f'Usage capture error: {e}')
            yield ('usage', {'input_tokens': 0, 'output_tokens': 0})


def _stream_openai_compatible(provider_id, turns, max_tokens, base_url=None):
    messages = _build_openai_messages(turns)
    model = PROVIDERS[provider_id]['model']
    client = _openai_compatible_client(provider_id, base_url=base_url)
    try:
        stream = client.chat.completions.create(
            model=model, max_tokens=max_tokens, messages=messages,
            stream=True, stream_options={'include_usage': True},
        )
    except BadRequestError:
        # Some OpenAI-compatible endpoints don't support stream_options — retry without it;
        # usage will stay at 0 for this call rather than the request failing outright.
        stream = client.chat.completions.create(
            model=model, max_tokens=max_tokens, messages=messages, stream=True,
        )
    input_tokens = output_tokens = 0
    for event in stream:
        if event.choices and event.choices[0].delta and event.choices[0].delta.content:
            yield ('text', event.choices[0].delta.content)
        if event.usage:
            input_tokens, output_tokens = event.usage.prompt_tokens, event.usage.completion_tokens
    yield ('usage', {'input_tokens': input_tokens, 'output_tokens': output_tokens})


def _stream_gemini(turns, max_tokens):
    contents = _build_gemini_contents(turns)
    client = _gemini_client()
    stream = client.models.generate_content_stream(
        model=PROVIDERS['gemini']['model'], contents=contents,
        config=_gemini_config(max_tokens),
    )
    input_tokens = output_tokens = 0
    for chunk in stream:
        try:
            if chunk.text:
                yield ('text', chunk.text)
        except Exception:
            pass  # chunk carries no text (e.g. safety-filtered) — skip it, don't fail the stream
        if chunk.usage_metadata:
            input_tokens  = chunk.usage_metadata.prompt_token_count or input_tokens
            output_tokens = chunk.usage_metadata.candidates_token_count or output_tokens
    yield ('usage', {'input_tokens': input_tokens, 'output_tokens': output_tokens})


def stream_completion(provider_id, turns, max_tokens):
    cfg = PROVIDERS[provider_id]
    kind = cfg['kind']
    if kind == 'anthropic':
        yield from _stream_anthropic(turns, max_tokens)
    elif kind == 'openai_compatible':
        yield from _stream_openai_compatible(provider_id, turns, max_tokens, base_url=cfg.get('base_url'))
    elif kind == 'gemini':
        yield from _stream_gemini(turns, max_tokens)
    else:
        raise ValueError(f'Unknown provider kind: {kind}')


# ── Non-streaming completions ────────────────────────────────────────────────────
# Used by routes that only need the final text (no incremental output to the client),
# so they call each SDK's native non-streaming method instead of draining a stream.

def _complete_anthropic(turns, max_tokens):
    messages = _build_anthropic_messages(turns)
    message = _anthropic_client().messages.create(
        model=PROVIDERS['anthropic']['model'], max_tokens=max_tokens, messages=messages,
    )
    text = message.content[0].text
    usage = {'input_tokens': message.usage.input_tokens, 'output_tokens': message.usage.output_tokens}
    return text, usage


def _complete_openai_compatible(provider_id, turns, max_tokens, base_url=None):
    messages = _build_openai_messages(turns)
    client = _openai_compatible_client(provider_id, base_url=base_url)
    response = client.chat.completions.create(
        model=PROVIDERS[provider_id]['model'], max_tokens=max_tokens, messages=messages,
    )
    text = response.choices[0].message.content
    usage = {'input_tokens': response.usage.prompt_tokens, 'output_tokens': response.usage.completion_tokens} if response.usage else {'input_tokens': 0, 'output_tokens': 0}
    return text, usage


def _complete_gemini(turns, max_tokens):
    contents = _build_gemini_contents(turns)
    client = _gemini_client()
    response = client.models.generate_content(
        model=PROVIDERS['gemini']['model'], contents=contents,
        config=_gemini_config(max_tokens),
    )
    text = response.text or ''
    if response.usage_metadata:
        usage = {
            'input_tokens': response.usage_metadata.prompt_token_count or 0,
            'output_tokens': response.usage_metadata.candidates_token_count or 0,
        }
    else:
        usage = {'input_tokens': 0, 'output_tokens': 0}
    return text, usage


def complete(provider_id, turns, max_tokens):
    """Returns (text, usage_dict) for a single non-streamed completion."""
    cfg = PROVIDERS[provider_id]
    kind = cfg['kind']
    if kind == 'anthropic':
        return _complete_anthropic(turns, max_tokens)
    elif kind == 'openai_compatible':
        return _complete_openai_compatible(provider_id, turns, max_tokens, base_url=cfg.get('base_url'))
    elif kind == 'gemini':
        return _complete_gemini(turns, max_tokens)
    else:
        raise ValueError(f'Unknown provider kind: {kind}')
