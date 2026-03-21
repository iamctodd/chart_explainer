from flask import Flask, render_template, request, jsonify, Response, stream_with_context
import anthropic
import os
import base64
import markdown
import json

app = Flask(__name__)

# Initialize Anthropic client
claude = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

# Shared analysis prompt used by all endpoints
ANALYSIS_PROMPT = """Analyze this chart/graph and provide:

1. **What this shows**: Explain what data is being presented (2-3 sentences)
2. **What this chart is really saying**: What are the main takeaways or patterns?
3. **What this does NOT show**: Important limitations or what's missing
4. **What people often misread here**: Common ways people might misread this
5. **What could be improved**: How to make this chart easier to understand

Be clear and helpful, not condescending. If the axes are misleading or there are visual tricks, point them out."""


def make_image_message(image_base64, media_type):
    """Build the first user message containing the chart image and analysis prompt."""
    return {
        "role": "user",
        "content": [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": image_base64,
                },
            },
            {"type": "text", "text": ANALYSIS_PROMPT},
        ],
    }


def sse_event(event, data):
    """Format a single SSE event string."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


# ── Non-streaming endpoints (kept for backwards compatibility) ─────────────────

def explain_chart(image_base64, media_type):
    """Send image to Claude for explanation"""
    try:
        message = claude.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1500,
            messages=[make_image_message(image_base64, media_type)],
        )
        return message.content[0].text
    except Exception as e:
        return f"Error: {str(e)}"


def follow_up_chart(image_base64, media_type, question, conversation_history, analysis_raw=''):
    """Send a follow-up question to Claude with full chart context and conversation history"""
    try:
        messages = [make_image_message(image_base64, media_type)]
        # Insert the initial analysis as an assistant turn so Claude doesn't repeat it
        if analysis_raw:
            messages.append({"role": "assistant", "content": analysis_raw})
        for turn in conversation_history:
            messages.append({"role": turn["role"], "content": turn["content"]})
        messages.append({"role": "user", "content": question})

        message = claude.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            messages=messages,
        )
        return message.content[0].text
    except Exception as e:
        return f"Error: {str(e)}"


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/analyze', methods=['POST'])
def analyze():
    if 'chart' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400

    file = request.files['chart']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    image_bytes = file.read()
    image_data = base64.b64encode(image_bytes).decode('utf-8')
    media_type = file.content_type
    if not media_type or not media_type.startswith('image/'):
        media_type = 'image/png'

    explanation_markdown = explain_chart(image_data, media_type)
    explanation_html = markdown.markdown(explanation_markdown, extensions=['extra', 'nl2br'])

    return jsonify({
        'explanation': explanation_html,
        'image': f"data:{media_type};base64,{image_data}",
    })


@app.route('/followup', methods=['POST'])
def followup():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Invalid request'}), 400

    question = data.get('question', '').strip()
    image_data_url = data.get('image', '')
    conversation_history = data.get('conversation_history', [])

    if not question:
        return jsonify({'error': 'No question provided'}), 400
    if not image_data_url:
        return jsonify({'error': 'No image provided'}), 400

    if ',' in image_data_url:
        header, image_base64 = image_data_url.split(',', 1)
        media_type = header.split(':')[1].split(';')[0] if ':' in header else 'image/png'
    else:
        image_base64 = image_data_url
        media_type = 'image/png'

    analysis_raw = data.get('analysis_raw', '')
    answer_markdown = follow_up_chart(image_base64, media_type, question, conversation_history, analysis_raw)
    answer_html = markdown.markdown(answer_markdown, extensions=['extra', 'nl2br'])

    return jsonify({'answer': answer_html, 'answer_raw': answer_markdown})


# ── Streaming endpoints ────────────────────────────────────────────────────────

@app.route('/analyze_stream', methods=['POST'])
def analyze_stream():
    if 'chart' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400

    file = request.files['chart']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    image_bytes = file.read()
    image_base64 = base64.b64encode(image_bytes).decode('utf-8')
    media_type = file.content_type
    if not media_type or not media_type.startswith('image/'):
        media_type = 'image/png'

    image_data_url = f"data:{media_type};base64,{image_base64}"

    def generate():
        try:
            # Send image first so the UI can display it while Claude streams
            yield sse_event('image', {'image': image_data_url})

            with claude.messages.stream(
                model="claude-sonnet-4-20250514",
                max_tokens=1500,
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
def followup_stream():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Invalid request'}), 400

    question = data.get('question', '').strip()
    image_data_url = data.get('image', '')
    conversation_history = data.get('conversation_history', [])

    if not question:
        return jsonify({'error': 'No question provided'}), 400
    if not image_data_url:
        return jsonify({'error': 'No image provided'}), 400

    if ',' in image_data_url:
        header, image_base64 = image_data_url.split(',', 1)
        media_type = header.split(':')[1].split(';')[0] if ':' in header else 'image/png'
    else:
        image_base64 = image_data_url
        media_type = 'image/png'

    analysis_raw = data.get('analysis_raw', '')
    messages = [make_image_message(image_base64, media_type)]
    # Insert the initial analysis as an assistant turn so Claude doesn't repeat it
    if analysis_raw:
        messages.append({"role": "assistant", "content": analysis_raw})
    for turn in conversation_history:
        messages.append({"role": turn["role"], "content": turn["content"]})
    messages.append({"role": "user", "content": question})

    def generate():
        try:
            with claude.messages.stream(
                model="claude-sonnet-4-20250514",
                max_tokens=1024,
                messages=messages,
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
