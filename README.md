# 📊 ChartHawk

**Stop pretending you understand every chart. Get clear explanations in seconds.**

ChartHawk is a web app that analyzes charts and visualizations using AI, providing plain-English explanations of what the data actually shows, what it doesn't show, and common misinterpretations.

🔗 **Live Demo:** [ChartHawk.info](https://charthawk.info)

---

## Why ChartHawk?

We've all been in meetings where someone presents a complex chart and everyone nods along. The data literacy gap is real, and it's embarrassing to admit when you don't understand a visualization.

ChartHawk gives you:
- **What it shows**: Clear explanation of the data and trends
- **Key insights**: Main takeaways you should notice
- **What it doesn't show**: Important limitations and missing context
- **Common misinterpretations**: How people often misread the chart

---

## Features

✅ **Upload any chart** - PNG, JPG, GIF support  
✅ **AI-powered analysis** - Uses Claude Sonnet 4.5 for accurate interpretation  
✅ **Multi-chart history** - Analyze multiple charts in one session  
✅ **Copy to clipboard** - One-click sharing of analysis  
✅ **Privacy-focused** - No login required, session-based storage  
✅ **Fast & simple** - No complicated setup or configuration  

---

## Tech Stack

- **Frontend**: Vanilla JavaScript, HTML/CSS
- **Backend**: Python Flask
- **AI**: Anthropic Claude API (Sonnet 4.5)
- **Deployment**: Railway
- **Feedback**: Formspree

---

## Getting Started

### Prerequisites

- Python 3.8+
- Anthropic API key ([get one here](https://console.anthropic.com))

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/iamctodd/charthawk.git
   cd charthawk/web_app
   ```

2. **Create virtual environment**
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set environment variables**
   ```bash
   export ANTHROPIC_API_KEY="your-api-key-here"
   export PORT=5001  # Optional, defaults to 5000

   # Optional — enables additional models in the model selector.
   # Only providers with a key set will appear in the dropdown.
   export OPENAI_API_KEY="your-openai-key"   # GPT-4o
   export GOOGLE_API_KEY="your-google-key"   # Gemini
   export XAI_API_KEY="your-xai-key"         # Grok
   ```

5. **Run the app**
   ```bash
   python3 app.py
   ```

6. **Open your browser**
   ```
   http://localhost:5001
   ```

---

## Deployment

### Railway (Recommended)

1. Fork this repository
2. Connect your GitHub repo to Railway
3. Set environment variable: `ANTHROPIC_API_KEY` (optionally also `OPENAI_API_KEY`, `GOOGLE_API_KEY`, `XAI_API_KEY` for additional models)
4. Set root directory to `web_app`
5. Deploy!

Railway will automatically detect the Python app and use the provided `railway.json` configuration.

---

## Project Structure

```
charthawk/
├── web_app/              # Web application
│   ├── app.py           # Flask backend
│   ├── templates/
│   │   └── index.html   # Frontend UI
│   ├── requirements.txt # Python dependencies
│   └── railway.json     # Railway config
└── slack_app/           # Slack bot (experimental)
    └── bot.py
```

---

## Usage

1. **Upload a chart** - Drag and drop or click to upload any chart image
2. **Get explanation** - AI analyzes and explains the visualization
3. **Review insights** - Understand what the chart shows and doesn't show
4. **Copy analysis** - Click the copy button to share the explanation
5. **Upload more** - Analyze multiple charts in one session

---

## API Costs

ChartHawk uses the Anthropic Claude API. Approximate costs:
- ~$0.015 per chart analysis (Sonnet 4.5)
- Free tier credits available for new accounts
- Monitor usage in [Anthropic Console](https://console.anthropic.com)

---

## Roadmap

See [ROADMAP.md](ROADMAP.md) for planned features and improvements.

---

## Contributing

Contributions welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

---

## Feedback

Found a bug? Have a feature request? 

- Use the "Send Feedback" button in the app
- Open an issue on GitHub
- Reach out on [your contact method]

---

## License

MIT License - see LICENSE file for details

---

## Acknowledgments

- Built with [Anthropic Claude](https://www.anthropic.com/claude)
- Deployed on [Railway](https://railway.app)
- Feedback powered by [Formspree](https://formspree.io)

---

**Made by [@iamctodd](https://github.com/iamctodd)** | Built in public 🚀
