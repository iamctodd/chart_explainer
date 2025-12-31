from flask import Flask, request, jsonify
from slack_sdk import WebClient
import anthropic
import requests
import os
import base64

app = Flask(__name__)

# Initialize clients
slack_client = WebClient(token=os.environ.get("SLACK_BOT_TOKEN"))
claude = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

def get_image_from_slack(file_url, bot_token):
    """Download image from Slack"""
    headers = {"Authorization": f"Bearer {bot_token}"}
    response = requests.get(file_url, headers=headers)
    return base64.b64encode(response.content).decode('utf-8')

def explain_chart(image_base64, file_type):
    """Send image to Claude for explanation"""
    message = claude.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": f"image/{file_type}",
                        "data": image_base64,
                    },
                },
                {
                    "type": "text",
                    "text": """Analyze this chart/graph and provide:

1. **What this shows**: Explain what data is being presented (2-3 sentences)
2. **Key insights**: What are the main takeaways or patterns?
3. **What this does NOT show**: Important limitations or what's missing
4. **Potential misinterpretations**: Common ways people might misread this

Be clear and helpful, not condescending. If the axes are misleading or there are visual tricks, point them out."""
                }
            ],
        }]
    )
    return message.content[0].text

@app.route("/slack/events", methods=["POST"])
def slack_events():
    data = request.get_json()
    
    print("Received:", data.get("type"))
    
    # Handle URL verification
    if data.get("type") == "url_verification":
        return jsonify({"challenge": data["challenge"]})
    
    # Handle events
    if data.get("type") == "event_callback":
        event = data["event"]
        
        # Ignore bot messages
        if event.get("bot_id"):
            return jsonify({"ok": True})
        
        # Handle app mentions or DMs with files
        if "files" in event:
            for file in event["files"]:
                if file["mimetype"].startswith("image/"):
                    try:
                        file_type = file["mimetype"].split("/")[1]
                        image_data = get_image_from_slack(
                            file["url_private"],
                            os.environ.get("SLACK_BOT_TOKEN")
                        )
                        
                        explanation = explain_chart(image_data, file_type)
                        
                        # Reply in thread or channel
                        slack_client.chat_postMessage(
                            channel=event["channel"],
                            text=explanation,
                            thread_ts=event.get("ts")
                        )
                    except Exception as e:
                        print(f"Error: {e}")
                        slack_client.chat_postMessage(
                            channel=event["channel"],
                            text=f"Sorry, I had trouble analyzing that: {str(e)}",
                            thread_ts=event.get("ts")
                        )
    
    return jsonify({"ok": True})

if __name__ == "__main__":
    print("Bot starting on port 3000...")
    app.run(port=3000, debug=True)