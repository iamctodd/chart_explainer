from flask import Flask, render_template, request, jsonify
import anthropic
import os
import base64
import markdown

app = Flask(__name__)

# Initialize Anthropic client
claude = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

def explain_chart(image_base64, media_type):
    """Send image to Claude for explanation"""
    try:
        message = claude.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1500,
            messages=[{
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
                    {
                        "type": "text",
                        "text": """Analyze this chart/graph and provide:

1. **What this shows**: Explain what data is being presented (2-3 sentences)
2. **What this chart is really saying**: What are the main takeaways or patterns?
3. **What this does NOT show**: Important limitations or what's missing
4. **What people often misread here**: Common ways people might misread this
5. **What could be improved**: How to make this chart easier to understand

Be clear and helpful, not condescending. If the axes are misleading or there are visual tricks, point them out."""
                    }
                ],
            }]
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
    
    # Read and encode image
    image_bytes = file.read()
    image_data = base64.b64encode(image_bytes).decode('utf-8')
    
    # Determine media type
    media_type = file.content_type
    if not media_type or not media_type.startswith('image/'):
        media_type = 'image/png'  # default
    
    # Get explanation
    explanation_markdown = explain_chart(image_data, media_type)
    
    # Convert markdown to HTML
    explanation_html = markdown.markdown(
        explanation_markdown,
        extensions=['extra', 'nl2br']
    )
    
    # Return both the explanation and the image data for preview
    return jsonify({
        'explanation': explanation_html,
        'image': f"data:{media_type};base64,{image_data}"
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)