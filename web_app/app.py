from flask import Flask, render_template, request, jsonify, Response, stream_with_context
from functools import wraps
import anthropic
import os
import base64
import markdown
import json
import re
import io
import hashlib
import secrets
from PIL import Image
from supabase import create_client

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # 5 MB upload limit

@app.errorhandler(413)
def too_large(e):
    return jsonify({'error': 'Image must be under 5MB. Please resize and try again.'}), 413

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


def hash_api_key(raw_key):
    return hashlib.sha256(raw_key.encode()).hexdigest()


def calculate_cost(input_tokens, output_tokens):
    """Cost in USD — claude-sonnet-4-6: $3/1M input, $15/1M output"""
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


def require_api_key(f):
    """Authenticate via a stable sk-hawk-... API key stored in api_keys table."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not admin_client:
            return jsonify({'error': 'Server misconfigured'}), 500
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer sk-hawk-'):
            return jsonify({'error': 'Valid API key required (Bearer sk-hawk-...)'}), 401
        raw_key  = auth_header[7:]
        key_hash = hash_api_key(raw_key)
        try:
            result = admin_client.from_('api_keys') \
                .select('id,user_id') \
                .eq('key_hash', key_hash) \
                .single().execute()
            if not result.data:
                raise ValueError('Key not found')
            request.user_id = result.data['user_id']
            # Update last_used_at — fire and forget
            try:
                from datetime import datetime, timezone
                admin_client.from_('api_keys') \
                    .update({'last_used_at': datetime.now(timezone.utc).isoformat()}) \
                    .eq('id', result.data['id']).execute()
            except Exception:
                pass
        except Exception:
            return jsonify({'error': 'Invalid or revoked API key'}), 401
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
            model="claude-sonnet-4-6", max_tokens=1500,
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
            model="claude-sonnet-4-6", max_tokens=1024, messages=messages,
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
                model="claude-sonnet-4-6", max_tokens=1500,
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
                model="claude-sonnet-4-6", max_tokens=1024, messages=messages,
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


# ── API Key management routes ─────────────────────────────────────────────────

@app.route('/api/keys', methods=['GET'])
@require_auth
def list_api_keys():
    if not admin_client:
        return jsonify({'error': 'Server misconfigured'}), 500
    try:
        resp = admin_client.from_('api_keys') \
            .select('id,name,key_prefix,created_at,last_used_at') \
            .eq('user_id', request.user_id) \
            .order('created_at', desc=True) \
            .execute()
        return jsonify({'keys': resp.data or []})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/keys', methods=['POST'])
@require_auth
def create_api_key():
    if not admin_client:
        return jsonify({'error': 'Server misconfigured'}), 500
    body = request.get_json() or {}
    name = body.get('name', '').strip() or 'My API key'
    raw_key    = 'sk-hawk-' + secrets.token_urlsafe(32)
    key_prefix = raw_key[:16] + '…'
    key_hash   = hash_api_key(raw_key)
    try:
        admin_client.from_('api_keys').insert({
            'user_id':    request.user_id,
            'name':       name,
            'key_hash':   key_hash,
            'key_prefix': key_prefix,
        }).execute()
        # Return the raw key ONCE — never stored, never retrievable again
        return jsonify({'key': raw_key, 'prefix': key_prefix, 'name': name}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/keys/<key_id>', methods=['DELETE'])
@require_auth
def delete_api_key(key_id):
    if not admin_client:
        return jsonify({'error': 'Server misconfigured'}), 500
    try:
        admin_client.from_('api_keys') \
            .delete() \
            .eq('id', key_id) \
            .eq('user_id', request.user_id) \
            .execute()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── Programmatic API (API key auth) ───────────────────────────────────────────

@app.route('/api/v1/analyze', methods=['POST'])
@require_api_key
def api_v1_analyze():
    """Synchronous JSON endpoint for programmatic use (Claude Skills, scripts, etc.)"""
    if 'chart' not in request.files:
        return jsonify({'error': 'No file uploaded. Send chart as multipart/form-data field "chart".'}), 400
    file = request.files['chart']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    image_bytes  = file.read()
    image_base64 = base64.b64encode(image_bytes).decode('utf-8')
    media_type   = file.content_type
    if not media_type or not media_type.startswith('image/'):
        media_type = 'image/png'
    try:
        message = claude.messages.create(
            model='claude-sonnet-4-6',
            max_tokens=1500,
            messages=[make_image_message(image_base64, media_type)],
        )
        raw_text = message.content[0].text
        # Track usage
        try:
            if admin_client:
                admin_client.table('usage').insert({
                    'user_id':       request.user_id,
                    'chart_id':      None,
                    'event':         'analyze',
                    'input_tokens':  message.usage.input_tokens,
                    'output_tokens': message.usage.output_tokens,
                    'cost_usd':      calculate_cost(message.usage.input_tokens, message.usage.output_tokens),
                }).execute()
        except Exception as ue:
            print(f'Usage tracking error: {ue}')
        return jsonify({
            'analysis': raw_text,
            'filename': file.filename,
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── Gallery helpers ────────────────────────────────────────────────────────────

def make_thumbnail(image_base64, max_width=400):
    """Resize a base64 image to a compact thumbnail for gallery cards."""
    try:
        raw = base64.b64decode(image_base64.split(',')[-1])
        img = Image.open(io.BytesIO(raw))
        ratio = min(max_width / img.width, 1.0)
        new_size = (int(img.width * ratio), int(img.height * ratio))
        img = img.resize(new_size, Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format='WEBP', quality=70)
        return 'data:image/webp;base64,' + base64.b64encode(buf.getvalue()).decode()
    except Exception as e:
        print(f'Thumbnail generation failed: {e}')
        return None


def generate_gallery_summary(analysis_raw):
    """Ask Claude to extract 3 insights + 3 improvements as JSON."""
    prompt = (
        'From this chart analysis, extract exactly:\n'
        '- 3 key insights (1 sentence each)\n'
        '- 3 improvement suggestions (1 sentence each)\n\n'
        'Return ONLY valid JSON with no markdown fencing:\n'
        '{"insights": ["...", "...", "..."], "improvements": ["...", "...", "..."]}\n\n'
        f'Analysis:\n{analysis_raw[:3000]}'
    )
    try:
        msg = claude.messages.create(
            model='claude-sonnet-4-6',
            max_tokens=300,
            messages=[{'role': 'user', 'content': prompt}],
        )
        raw_text = msg.content[0].text.strip()
        raw_text = re.sub(r'^```[a-z]*\n?', '', raw_text, flags=re.MULTILINE).strip('`').strip()
        return json.loads(raw_text)
    except Exception as e:
        print(f'Summary generation failed: {e}')
        return {'insights': [], 'improvements': []}


# ── Gallery & share routes ─────────────────────────────────────────────────────

@app.route('/gallery')
def gallery_page():
    return render_template('gallery.html')


@app.route('/share/<chart_id>')
def share_page(chart_id):
    return render_template('share.html', chart_id=chart_id)


@app.route('/api/gallery')
def gallery_feed():
    """Paginated public charts feed — no auth required."""
    if not admin_client:
        return jsonify({'error': 'Server misconfigured'}), 500
    page   = max(0, int(request.args.get('page', 0)))
    limit  = 20
    offset = page * limit
    try:
        resp = (
            admin_client.from_('charts')
            .select('id,filename,display_name,thumbnail_data,gallery_summary,created_at')
            .eq('is_public', True)
            .order('created_at', desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )
        return jsonify({'charts': resp.data or [], 'page': page})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/chart/<chart_id>/publish', methods=['POST'])
@require_auth
def toggle_publish(chart_id):
    """Toggle is_public; generate thumbnail + gallery summary on first publish."""
    if not admin_client:
        return jsonify({'error': 'Server misconfigured'}), 500
    body      = request.get_json() or {}
    is_public = bool(body.get('is_public', False))
    update    = {'is_public': is_public}
    try:
        existing = (
            admin_client.from_('charts')
            .select('gallery_summary,thumbnail_data,analysis_raw,image_data')
            .eq('id', chart_id)
            .eq('user_id', request.user_id)
            .single()
            .execute()
        )
        if not existing.data:
            return jsonify({'error': 'Chart not found'}), 404

        if is_public:
            row = existing.data
            if not row.get('gallery_summary'):
                update['gallery_summary'] = generate_gallery_summary(row.get('analysis_raw', ''))
            if not row.get('thumbnail_data') and row.get('image_data'):
                thumb = make_thumbnail(row['image_data'])
                if thumb:
                    update['thumbnail_data'] = thumb

        admin_client.from_('charts').update(update) \
            .eq('id', chart_id).eq('user_id', request.user_id).execute()
        return jsonify({'ok': True, 'is_public': is_public})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/share/<chart_id>')
def share_data(chart_id):
    """Return full public chart data + messages for the share page."""
    if not admin_client:
        return jsonify({'error': 'Server misconfigured'}), 500
    try:
        chart_resp = (
            admin_client.from_('charts')
            .select('id,filename,display_name,image_data,explanation,analysis_raw,created_at')
            .eq('id', chart_id)
            .eq('is_public', True)
            .single()
            .execute()
        )
        if not chart_resp.data:
            return jsonify({'error': 'Chart not found or not public'}), 404

        msgs_resp = (
            admin_client.from_('messages')
            .select('role,content,html,created_at')
            .eq('chart_id', chart_id)
            .order('created_at', desc=False)
            .execute()
        )
        return jsonify({
            'chart':    chart_resp.data,
            'messages': msgs_resp.data or [],
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/chart/<chart_id>/comments', methods=['GET'])
def get_comments(chart_id):
    """List comments for a chart (public or own)."""
    if not admin_client:
        return jsonify({'error': 'Server misconfigured'}), 500
    try:
        # Verify chart is public (anyone can read) or skip check for now via admin client
        resp = (
            admin_client.from_('comments')
            .select('id,author_name,content,created_at,updated_at,user_id')
            .eq('chart_id', chart_id)
            .order('created_at', desc=False)
            .execute()
        )
        return jsonify({'comments': resp.data or []})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/chart/<chart_id>/comments', methods=['POST'])
@require_auth
def add_comment(chart_id):
    """Add a comment to a public chart."""
    if not admin_client:
        return jsonify({'error': 'Server misconfigured'}), 500
    body    = request.get_json() or {}
    content = body.get('content', '').strip()
    if not content:
        return jsonify({'error': 'Comment cannot be empty'}), 400
    if len(content) > 1000:
        return jsonify({'error': 'Comment must be under 1000 characters'}), 400

    # Resolve author name from auth
    try:
        user_resp = supabase_client.auth.get_user(request.headers.get('Authorization', '')[7:])
        author_name = (user_resp.user.user_metadata or {}).get('full_name') or user_resp.user.email or 'Anonymous'
    except Exception:
        author_name = 'Anonymous'

    try:
        admin_client.from_('comments').insert({
            'chart_id':    chart_id,
            'user_id':     request.user_id,
            'author_name': author_name,
            'content':     content,
        }).execute()
        return jsonify({'ok': True}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/comment/<comment_id>', methods=['PUT'])
@require_auth
def edit_comment(comment_id):
    """Edit own comment."""
    if not admin_client:
        return jsonify({'error': 'Server misconfigured'}), 500
    body    = request.get_json() or {}
    content = body.get('content', '').strip()
    if not content:
        return jsonify({'error': 'Comment cannot be empty'}), 400
    if len(content) > 1000:
        return jsonify({'error': 'Comment must be under 1000 characters'}), 400
    try:
        from datetime import datetime, timezone
        resp = (
            admin_client.from_('comments')
            .update({'content': content, 'updated_at': datetime.now(timezone.utc).isoformat()})
            .eq('id', comment_id)
            .eq('user_id', request.user_id)
            .execute()
        )
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/comment/<comment_id>', methods=['DELETE'])
@require_auth
def delete_comment(comment_id):
    """Delete own comment."""
    if not admin_client:
        return jsonify({'error': 'Server misconfigured'}), 500
    try:
        admin_client.from_('comments') \
            .delete() \
            .eq('id', comment_id) \
            .eq('user_id', request.user_id) \
            .execute()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
