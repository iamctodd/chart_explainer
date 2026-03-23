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

SUPABASE_SERVICE_KEY = os.environ.get('SUPABASE_SERVICE_KEY', '')
POSTHOG_KEY = os.environ.get('POSTHOG_KEY', '')
admin_client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY) if SUPABASE_SERVICE_KEY else None

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


def calculate_cost(input_tokens, output_tokens):
    """Cost in USD — claude-sonnet-4-20250514: $3/1M input, $15/1M output"""
    return round((input_tokens * 3.0 + output_tokens * 15.0) / 1_000_000, 6)

def require_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return jsonify({'error': 'Authentication required'}), 401
        token = auth_header[7:]
        try:
            resp = supabase_client.auth.get_user(token)
            if not resp.user:
                raise ValueError('No user')
            if not resp.user.user_metadata.get('is_admin'):
                return jsonify({'error': 'Admin access required'}), 403
            request.user_id = resp.user.id
            request.admin_user = resp.user
        except Exception:
            return jsonify({'error': 'Unauthorized'}), 401
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
    return render_template('index.html', posthog_key=POSTHOG_KEY)


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
                # After text stream exhausted, capture usage
                try:
                    final_msg = stream.get_final_message()
                    usage = final_msg.usage
                    user_id = getattr(request, 'user_id', None)
                    if user_id and admin_client:
                        admin_client.table('usage').insert({
                            'user_id': user_id,
                            'chart_id': None,
                            'event': 'analyze',
                            'input_tokens': usage.input_tokens,
                            'output_tokens': usage.output_tokens,
                            'cost_usd': calculate_cost(usage.input_tokens, usage.output_tokens)
                        }).execute()
                except Exception as ue:
                    print(f'Usage tracking error: {ue}')
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
                # After text stream exhausted, capture usage
                try:
                    final_msg = stream.get_final_message()
                    usage = final_msg.usage
                    user_id = getattr(request, 'user_id', None)
                    if user_id and admin_client:
                        admin_client.table('usage').insert({
                            'user_id': user_id,
                            'chart_id': data.get('chart_id'),
                            'event': 'followup',
                            'input_tokens': usage.input_tokens,
                            'output_tokens': usage.output_tokens,
                            'cost_usd': calculate_cost(usage.input_tokens, usage.output_tokens)
                        }).execute()
                except Exception as ue:
                    print(f'Usage tracking error: {ue}')
            yield sse_event('done', {})
        except Exception as e:
            yield sse_event('error', {'error': str(e)})

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )


# ── Admin routes ────────────────────────────────────────────────────────────

@app.route('/admin')
def admin_page():
    return render_template('admin.html')


@app.route('/admin/api/stats')
@require_admin
def admin_stats():
    try:
        all_usage = admin_client.table('usage').select('input_tokens,output_tokens,cost_usd,created_at').execute()
        rows = all_usage.data or []

        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()

        total_cost    = sum(r['cost_usd'] for r in rows)
        total_calls   = len(rows)
        total_input   = sum(r['input_tokens'] for r in rows)
        total_output  = sum(r['output_tokens'] for r in rows)
        month_rows    = [r for r in rows if r['created_at'] >= month_start]
        month_cost    = sum(r['cost_usd'] for r in month_rows)
        month_calls   = len(month_rows)

        # Count distinct users
        all_users = admin_client.auth.admin.list_users()
        user_count = len(all_users) if all_users else 0

        return jsonify({
            'all_time':   {'cost': total_cost,  'calls': total_calls,  'input_tokens': total_input, 'output_tokens': total_output},
            'this_month': {'cost': month_cost,  'calls': month_calls},
            'user_count': user_count
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/admin/api/users')
@require_admin
def admin_users():
    try:
        usage_data = admin_client.table('usage').select('user_id,input_tokens,output_tokens,cost_usd,event,created_at').execute()
        rows = usage_data.data or []

        # Aggregate by user_id
        stats = {}
        for row in rows:
            uid = row['user_id']
            if uid not in stats:
                stats[uid] = {'user_id': uid, 'analyses': 0, 'followups': 0,
                              'input_tokens': 0, 'output_tokens': 0, 'cost_usd': 0.0, 'last_used': None}
            s = stats[uid]
            if row['event'] == 'analyze':
                s['analyses'] += 1
            else:
                s['followups'] += 1
            s['input_tokens']  += row['input_tokens']
            s['output_tokens'] += row['output_tokens']
            s['cost_usd']      += row['cost_usd']
            if not s['last_used'] or row['created_at'] > s['last_used']:
                s['last_used'] = row['created_at']

        # Enrich with email/name/admin flag from auth
        auth_users = admin_client.auth.admin.list_users()
        email_map  = {
            u.id: {
                'email':    u.email,
                'name':     (u.user_metadata or {}).get('full_name', ''),
                'is_admin': (u.user_metadata or {}).get('is_admin', False),
                'created_at_user': str(u.created_at)
            }
            for u in auth_users
        }

        result = []
        for uid, s in stats.items():
            result.append({**s, **(email_map.get(uid, {'email': uid, 'name': '', 'is_admin': False, 'created_at_user': ''}))})

        # Add zero-usage users
        for u in auth_users:
            if u.id not in stats:
                result.append({
                    'user_id': u.id, 'email': u.email,
                    'name': (u.user_metadata or {}).get('full_name', ''),
                    'is_admin': (u.user_metadata or {}).get('is_admin', False),
                    'created_at_user': str(u.created_at),
                    'analyses': 0, 'followups': 0,
                    'input_tokens': 0, 'output_tokens': 0,
                    'cost_usd': 0.0, 'last_used': None
                })

        result.sort(key=lambda x: x['cost_usd'], reverse=True)
        return jsonify({'users': result})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/admin/api/promote', methods=['POST'])
@require_admin
def admin_promote():
    data       = request.get_json() or {}
    email      = data.get('email', '').strip().lower()
    grant      = data.get('grant', True)
    if not email:
        return jsonify({'error': 'Email required'}), 400
    try:
        auth_users = admin_client.auth.admin.list_users()
        target = next((u for u in auth_users if (u.email or '').lower() == email), None)
        if not target:
            return jsonify({'error': f'No user found with email {email}'}), 404
        meta = dict(target.user_metadata or {})
        meta['is_admin'] = grant
        admin_client.auth.admin.update_user_by_id(target.id, {'user_metadata': meta})
        return jsonify({'success': True, 'email': email, 'is_admin': grant})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
