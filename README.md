# Research Paper to Podcast Generator

Transform research papers into engaging podcast episodes using AI. This application takes a research paper (PDF or URL) and converts it into a conversational podcast script using Google's Gemini AI.

## Features

- Extract text from PDF files or web URLs
- Convert academic content into engaging podcast scripts
- Web interface for easy interaction
- (Coming soon) Integration with Murf.ai for text-to-speech

## Tech Stack

- **Backend**: Python, Flask
- **AI**: Google Gemini API
- **Frontend**: HTML, CSS, JavaScript
- **PDF Processing**: PyMuPDF (fitz)

## Prerequisites

- Python 3.8+
- Google Gemini API key
- (Optional) Murf.ai API key (for future audio generation)

## Setup

1. Clone this repository
2. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Create a `.env` file in the project root and add your API key:
   ```
   GEMINI_API_KEY=your_api_key_here
   ```

## Installation

### Using Virtual Environment (Recommended)

```bash
# Create virtual environment
python -m venv venv

# Activate on Windows
venv\Scripts\activate

# Activate on macOS/Linux
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Using uv (Alternative)

```bash
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt
```

## Usage

1. Run the application:
   ```
   python app.py
   ```
2. Open your browser and navigate to `http://localhost:5000`
3. Enter a PDF URL or upload a PDF file
4. Click "Generate Podcast" and wait for the magic to happen!

## Project Structure

```
research-podcast-generator/
├── app.py                 # Main Flask application
├── requirements.txt       # Python dependencies
├── .env                   # Environment variables
├── static/
│   ├── css/              # Stylesheets
│   └── js/               # Client-side scripts
├── templates/
│   └── index.html        # Main web interface
├── utils/
│   ├── pdf_extractor.py  # PDF text extraction
│   └── podcast_generator.py # AI podcast generation
└── README.md
```

## API Keys Setup

### Google Gemini API

1. Go to [Google AI Studio](https://makersuite.google.com/app/apikey)
2. Create a new API key
3. Add it to your `.env` file

## Future Improvements

- [ ] Integrate Murf.ai API for text-to-speech
- [ ] Add user accounts and history
- [ ] Support for more document formats
- [ ] Customizable podcast styles and voices
- [ ] Batch processing for multiple papers
- [ ] Export to audio files directly

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.