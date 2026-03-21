from flask import Flask, render_template, request, jsonify, Response, stream_with_context
from functools import wraps
import anthropic
import os
import base64
import markdown
import json
from supabase import create_client

app = Flask(__name__)

# ── Clients ────────────────────────────────────────────────────────────────────

claude = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

SUPABASE_URL      = os.environ.get('SUPABASE_URL',      'https://csjiymeycevxqmlmqcwc.supabase.co')
SUPABASE_ANON_KEY = os.environ.get('SUPABASE_ANON_KEY', 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImNzaml5bWV5Y2V2eHFtbG1xY3djIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzQwOTc1MDUsImV4cCI6MjA4OTY3MzUwNX0.JwUVn-NHrRCmuI8QDe_GEOJfTcT7lcHbh0Fhadrg4h0')
supabase_client   = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

# ── Auth ───────────────────────────────────────────────────────────────────────

def require_auth(f):
    """Verify Supabase JWT before allowing access to Claude API endpoints."""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return jsonify({'error': 'Authentication required'}), 401
        token = auth_header[7:]
        try:
            resp = supabase_client.auth.get_user(token)
            if not resp.user:
                raise ValueError('No user returned')
            request.user_id = resp.user.id
        except Exception:
            return jsonify({'error': 'Invalid or expired session. Please sign in again.'}), 401
        return f(*args, **kwargs)
    return decorated

# ── Shared prompt + helpers ────────────────────────────────────────────────────

ANALYSIS_PROMPT = """Analyze this chart/graph and provide:

1. **What this shows**: Explain what data is being presented (2-3 sentences)
2. **What this chart is really saying**: What are the main takeaways or patterns?
3. **What this does NOT show**: Important limitations or what's missing
4. **What people often misread here**: Common ways people might misread this
5. **What could be improved**: How to make this chart easier to understand

Be clear and helpful, not condescending. If the axes are misleading or there are visual tricks, point them out."""


def make_image_message(image_base64, media_type):
    return {
        "role": "user",
        "content": [
            {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": image_base64}},
            {"type": "text", "text": ANALYSIS_PROMPT},
        ],
    }


def sse_event(event, data):
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"

# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')


# Non-streaming endpoints kept for backwards compatibility (no auth required)

@app.route('/analyze', methods=['POST'])
def analyze():
    if 'chart' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    file = request.files['chart']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    image_bytes = file.read()
    image_data  = base64.b64encode(image_bytes).decode('utf-8')
    media_type  = file.content_type
    if not media_type or not media_type.startswith('image/'):
        media_type = 'image/png'
    try:
        message = claude.messages.create(
            model="claude-sonnet-4-20250514", max_tokens=1500,
            messages=[make_image_message(image_data, media_type)],
        )
        raw_text = message.content[0].text
        explanation_html = markdown.markdown(raw_text, extensions=['extra', 'nl2br'])
        return jsonify({'explanation': explanation_html, 'analysis_raw': raw_text, 'image': f"data:{media_type};base64,{image_data}"})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/followup', methods=['POST'])
def followup():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Invalid request'}), 400
    question             = data.get('question', '').strip()
    image_data_url       = data.get('image', '')
    conversation_history = data.get('conversation_history', [])
    analysis_raw         = data.get('analysis_raw', '')
    if not question:   return jsonify({'error': 'No question provided'}), 400
    if not image_data_url: return jsonify({'error': 'No image provided'}), 400
    if ',' in image_data_url:
        header, image_base64 = image_data_url.split(',', 1)
        media_type = header.split(':')[1].split(';')[0] if ':' in header else 'image/png'
    else:
        image_base64, media_type = image_data_url, 'image/png'
    messages = [make_image_message(image_base64, media_type)]
    if analysis_raw:
        messages.append({"role": "assistant", "content": analysis_raw})
    for turn in conversation_history:
        messages.append({"role": turn["role"], "content": turn["content"]})
    messages.append({"role": "user", "content": question})
    try:
        message = claude.messages.create(
            model="claude-sonnet-4-20250514", max_tokens=1024, messages=messages,
        )
        answer_markdown = message.content[0].text
        answer_html     = markdown.markdown(answer_markdown, extensions=['extra', 'nl2br'])
        return jsonify({'answer': answer_html, 'answer_raw': answer_markdown})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── Streaming endpoints (auth-protected) ──────────────────────────────────────

@app.route('/analyze_stream', methods=['POST'])
@require_auth
def analyze_stream():
    if 'chart' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    file = request.files['chart']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    image_bytes   = file.read()
    image_base64  = base64.b64encode(image_bytes).decode('utf-8')
    media_type    = file.content_type
    if not media_type or not media_type.startswith('image/'):
        media_type = 'image/png'
    image_data_url = f"data:{media_type};base64,{image_base64}"

    def generate():
        try:
            yield sse_event('image', {'image': image_data_url})
            with claude.messages.stream(
                model="claude-sonnet-4-20250514", max_tokens=1500,
                messages=[make_image_message(image_base64, media_type)],
            ) as stream:
                for text in stream.text_stream:
                    yield sse_event('text', {'chunk': text})
            yield sse_event('done', {})
        except Exception as e:
            yield sse_event('error', {'error': str(e)})

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )


@app.route('/followup_stream', methods=['POST'])
@require_auth
def followup_stream():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Invalid request'}), 400
    question             = data.get('question', '').strip()
    image_data_url       = data.get('image', '')
    conversation_history = data.get('conversation_history', [])
    analysis_raw         = data.get('analysis_raw', '')
    if not question:       return jsonify({'error': 'No question provided'}), 400
    if not image_data_url: return jsonify({'error': 'No image provided'}), 400
    if ',' in image_data_url:
        header, image_base64 = image_data_url.split(',', 1)
        media_type = header.split(':')[1].split(';')[0] if ':' in header else 'image/png'
    else:
        image_base64, media_type = image_data_url, 'image/png'

    messages = [make_image_message(image_base64, media_type)]
    if analysis_raw:
        messages.append({"role": "assistant", "content": analysis_raw})
    for turn in conversation_history:
        messages.append({"role": turn["role"], "content": turn["content"]})
    messages.append({"role": "user", "content": question})

    def generate():
        try:
            with claude.messages.stream(
                model="claude-sonnet-4-20250514", max_tokens=1024, messages=messages,
            ) as stream:
                for text in stream.text_stream:
                    yield sse_event('text', {'chunk': text})
            yield sse_event('done', {})
        except Exception as e:
            yield sse_event('error', {'error': str(e)})

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
