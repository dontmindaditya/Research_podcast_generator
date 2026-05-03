import os
import fitz  
import requests
from bs4 import BeautifulSoup
from flask import Flask, render_template, request, jsonify, send_from_directory
import tempfile
import sys
import uuid
import shutil
from pathlib import Path
import asyncio
import google.generativeai as genai
from dotenv import load_dotenv
from datetime import datetime
from murf import Murf

magic_available = False
try:
    import magic
    magic_available = True
except ImportError:
    try:
        import magic
        magic_available = True
    except Exception as e:
        print(f"Warning: python-magic not available. File type checking will be limited. Error: {e}")
        magic_available = False

# Import Murf.ai client
from utils.audio_utils import MurfAIClient

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['AUDIO_FOLDER'] = 'static/audio'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Ensure upload and audio directories exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['AUDIO_FOLDER'], exist_ok=True)

# Initialize Murf.ai client
try:
    murf_client = MurfAIClient()
except Exception as e:
    print(f"Warning: Could not initialize Murf.ai client: {e}")
    murf_client = None

# Configure Google's Generative AI
load_dotenv()
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
if not GEMINI_API_KEY:
    raise ValueError("Please set the GEMINI_API_KEY environment variable in .env file")

genai.configure(api_key=GEMINI_API_KEY)

# Initialize the model with safety settings
safety_settings = [
    {
        "category": "HARM_CATEGORY_HARASSMENT",
        "threshold": "BLOCK_NONE"
    },
    {
        "category": "HARM_CATEGORY_HATE_SPEECH",
        "threshold": "BLOCK_NONE"
    },
    {
        "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
        "threshold": "BLOCK_NONE"
    },
    {
        "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
        "threshold": "BLOCK_NONE"
    },
]

model = genai.GenerativeModel('gemini-1.5-flash', safety_settings=safety_settings)

def parse_script_sections(script_text):
    """Parse the script into intro, body, and conclusion sections."""
    sections = {
        'intro': '',
        'body': '',
        'conclusion': ''
    }
    
    if not script_text:
        return sections
    
    import re
    
    intro_match = re.search(r'\[INTRO\](.*?)\[/INTRO\]', script_text, re.DOTALL | re.IGNORECASE)
    body_match = re.search(r'\[BODY\](.*?)\[/BODY\]', script_text, re.DOTALL | re.IGNORECASE)
    conclusion_match = re.search(r'\[CONCLUSION\](.*?)\[/CONCLUSION\]', script_text, re.DOTALL | re.IGNORECASE)
    
    if intro_match:
        sections['intro'] = intro_match.group(1).strip()
    if body_match:
        sections['body'] = body_match.group(1).strip()
    if conclusion_match:
        sections['conclusion'] = conclusion_match.group(1).strip()
    
    if not any(sections.values()):
        parts = script_text.split('\n\n')
        if len(parts) >= 3:
            sections['intro'] = parts[0]
            sections['body'] = '\n\n'.join(parts[1:-1])
            sections['conclusion'] = parts[-1]
        elif len(parts) == 2:
            sections['intro'] = parts[0]
            sections['body'] = parts[1]
            sections['conclusion'] = parts[1]
        else:
            sections['body'] = script_text
    
    return sections

def extract_text_from_pdf(pdf_path):
    """Extract text from a PDF file."""
    try:
        # Check if the file exists and is a PDF
        if not os.path.exists(pdf_path):
            print(f"Error: File not found: {pdf_path}")
            return None
            
        # Verify it's a PDF file by extension if magic is not available
        if not pdf_path.lower().endswith('.pdf'):
            print("Error: File does not have a .pdf extension")
            return None
            
        # Additional check using magic if available
        if magic_available:
            try:
                mime = magic.Magic(mime=True)
                file_type = mime.from_file(pdf_path)
                if file_type != 'application/pdf':
                    print(f"Warning: File may not be a valid PDF. Detected type: {file_type}")
                    # Continue anyway since the extension is .pdf
            except Exception as e:
                print(f"Warning: Could not verify file type with magic: {e}")
        
        # Extract text from PDF
        with fitz.open(pdf_path) as doc:
            text = ""
            for page in doc:
                text += page.get_text()
        return text
    except Exception as e:
        print(f"Error extracting text from PDF: {e}")
        return None
    return text

def extract_text_from_url(url):
    """Extract text from a URL (handles both web pages and direct PDF links)."""
    try:
        response = requests.get(url, timeout=10)
        content_type = response.headers.get('content-type', '')
        
        if 'application/pdf' in content_type:
            # Handle direct PDF URLs
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
                tmp_file.write(response.content)
                return extract_text_from_pdf(tmp_file.name)
        else:
            # Handle web pages
            soup = BeautifulSoup(response.text, 'html.parser')
            # Remove script and style elements
            for script in soup(["script", "style"]):
                script.extract()
            return soup.get_text()
    except Exception as e:
        print(f"Error extracting text from URL: {e}")
        return None

def generate_podcast_script(text, mode='full', style='conversational'):
    """Generate a podcast script from the given text using Google's Gemini AI."""
    if not text or not text.strip():
        print("Error: Empty or invalid text provided for script generation")
        return None
        
    try:
        style_instructions = {
            'conversational': "Use a friendly, engaging tone as if chatting with colleagues. Include occasional asides.",
            'news': "Use a professional news anchor delivery style. Be formal, clear, and factual. No colloquialisms.",
            'casual': "Use an informal, laid-back style. Like discussing with friends over coffee. Use contractions and casual language.",
            'debate': "Present multiple viewpoints with balanced analysis. Acknowledge counterarguments and discuss implications."
        }
        
        style_guide = style_instructions.get(style, style_instructions['conversational'])
        
        if mode == 'summary':
            prompt_parts = [
                f"You are a professional podcast host. Create a SHORT, CONCISE summary of the following research paper. "
                f"Style: {style_guide}\n\n"
                "Structure your response exactly as follows with timestamps:\n"
                "[INTRO]\n[T: 00:00](Brief 2-3 sentence hook)\n[/INTRO]\n\n"
                "[BODY]\n[T: 00:30](Key findings - 3-5 bullet points max)\n[/BODY]\n\n"
                "[CONCLUSION]\n[T: 02:00](One sentence takeaway)\n[/CONCLUSION]\n\n"
                "Keep it brief - under 500 words total.\n\n"
                f"Here's the research paper content:\n{text[:15000]}"
            ]
        else:
            prompt_parts = [
                f"You are a professional podcast host. Transform the following research paper into an engaging podcast script. "
                f"Style: {style_guide}\n\n"
                "Structure your response exactly as follows with [T: MM:SS] timestamps for each section:\n"
                "[INTRO]\n[T: 00:00](Engaging introduction that hooks the listener)\n[SPEAKER NOTES: Mention paper title and authors]\n[/INTRO]\n\n"
                "[BODY]\n[T: 00:30](Key findings, methodology, results)\n[SPEAKER NOTES: Key data points to emphasize]\n[/BODY]\n\n"
                "[CONCLUSION]\n[T: 03:00](Conclusion and implications)\n[SPEAKER NOTES: Call to action for listeners]\n[/CONCLUSION]\n\n"
                f"Here's the research paper content:\n{text[:15000]}"
            ]
        
        print(f"Sending request to Gemini API... (mode: {mode}, style: {style})")
        
        max_retries = 3
        last_error = None
        
        for attempt in range(max_retries):
            try:
                print(f"Attempt {attempt + 1} of {max_retries}")
                response = model.generate_content(prompt_parts)
                
                if hasattr(response, 'text'):
                    return response.text
                    
                if hasattr(response, 'parts'):
                    parts_text = [part.text for part in response.parts if hasattr(part, 'text')]
                    if parts_text:
                        return ' '.join(parts_text)
                        
                if hasattr(response, 'candidates'):
                    for candidate in response.candidates:
                        if hasattr(candidate, 'content') and hasattr(candidate.content, 'parts'):
                            parts = [p.text for p in candidate.content.parts if hasattr(p, 'text')]
                            if parts:
                                return ' '.join(parts)
                
                print(f"Unexpected response format on attempt {attempt + 1}")
                
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    print(f"Retrying in {wait_time} seconds...")
                    import time
                    time.sleep(wait_time)
                    
            except Exception as e:
                last_error = e
                print(f"Attempt {attempt + 1} failed: {str(e)}")
                
                if attempt == max_retries - 1:
                    break
                    
                wait_time = 2 ** attempt
                print(f"Retrying in {wait_time} seconds...")
                import time
                time.sleep(wait_time)
        
        error_msg = "Failed to generate podcast script"
        if last_error:
            error_msg += f": {str(last_error)}"
        print(error_msg)
        return None
    except Exception as e:
        print(f"Error generating podcast script: {e}")
        return None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/static/audio/<filename>')
def serve_audio(filename):
    return send_from_directory(app.config['AUDIO_FOLDER'], filename)

@app.route('/generate', methods=['POST'])
def generate_podcast():
    """Handle podcast generation from a research paper URL or uploaded PDF."""
    try:
        paper_text = None
        voice_settings = {
            'intro': 'en-US-julia',
            'body': 'en-US-terrell',
            'conclusion': 'en-US-julia'
        }
        podcast_mode = 'full'
        podcast_style = 'conversational'
        
        # Case 1: Handle file upload
        if 'file' in request.files:
            file = request.files['file']
            if file.filename == '':
                return jsonify({'error': 'No selected file'}), 400
            
            # Check for voice settings in form data
            if request.form.get('voices'):
                import json
                voice_settings = json.loads(request.form.get('voices'))
            
            # Check for podcast mode in form data
            if request.form.get('podcast_mode'):
                podcast_mode = request.form.get('podcast_mode')
            
            # Check for podcast style in form data
            if request.form.get('podcast_style'):
                podcast_style = request.form.get('podcast_style')
            
            if file and file.filename.lower().endswith('.pdf'):
                # Save the uploaded file temporarily
                filename = str(uuid.uuid4()) + ".pdf"
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                
                # Extract text from the PDF
                paper_text = extract_text_from_pdf(filepath)
                
                # Clean up the uploaded file
                os.remove(filepath)
            else:
                return jsonify({'error': 'Invalid file type. Please upload a PDF.'}), 400

        # Case 2: Handle URL input
        elif request.is_json:
            data = request.get_json()
            url = data.get('source')
            if not url:
                return jsonify({'error': 'No URL provided'}), 400
            
            # Get voice settings if provided
            if data.get('voices'):
                voice_settings = data['voices']
            
            # Get podcast mode if provided
            if data.get('podcast_mode'):
                podcast_mode = data['podcast_mode']
            
            # Get podcast style if provided
            if data.get('podcast_style'):
                podcast_style = data['podcast_style']
            
            # Extract text from the URL
            paper_text = extract_text_from_url(url)
        
        # If no text could be extracted
        if not paper_text:
            return jsonify({'error': 'Could not extract text from the source.'}), 400
            
        # Generate podcast script using Gemini
        podcast_script = generate_podcast_script(paper_text, mode=podcast_mode, style=podcast_style)
        if not podcast_script:
            return jsonify({'error': 'Failed to generate podcast script'}), 500
            
        print("Successfully generated podcast script")
        
        # Save the script to a file (optional, but good for debugging)
        script_id = str(uuid.uuid4())
        script_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{script_id}.txt")
        with open(script_path, 'w', encoding='utf-8') as f:
            f.write(podcast_script)
        
        audio_url = None
        
        # Convert script to speech using Murf.ai with multi-voice support
        if not murf_client:
            return jsonify({
                'status': 'success',
                'script': podcast_script,
                'audio_url': None,
                'warning': 'Text-to-speech service not available'
            })
        
        try:
            # Parse script into sections
            sections = parse_script_sections(podcast_script)
            
            # Generate a unique filename for the audio
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            audio_filename = f"podcast_{timestamp}.mp3"
            audio_path = os.path.join(app.config['AUDIO_FOLDER'], audio_filename)
            
            # Process each section with corresponding voice
            section_voices = [
                ('intro', sections['intro'], voice_settings.get('intro', 'en-US-julia')),
                ('body', sections['body'], voice_settings.get('body', 'en-US-terrell')),
                ('conclusion', sections['conclusion'], voice_settings.get('conclusion', 'en-US-julia'))
            ]
            
            all_audio_data = bytearray()
            
            for section_name, section_text, voice_id in section_voices:
                if not section_text:
                    continue
                    
                print(f"[INFO] Processing {section_name} section with voice {voice_id}")
                
                # Split long sections into chunks
                max_chunk_length = 3000
                chunks = [section_text[i:i+max_chunk_length] 
                        for i in range(0, len(section_text), max_chunk_length)]
                
                for chunk_idx, chunk in enumerate(chunks):
                    client = Murf(api_key=murf_client.api_key)
                    response = client.text_to_speech.generate(
                        text=chunk,
                        voice_id=voice_id,
                        format="MP3",
                        channel_type="STEREO",
                        sample_rate=44100
                    )
                    
                    if response and hasattr(response, 'audio_file') and response.audio_file:
                        audio_url = response.audio_file
                        print(f"[INFO] Downloading {section_name} chunk audio from URL: {audio_url}")
                        audio_response = requests.get(audio_url)
                        if audio_response.status_code == 200:
                            all_audio_data.extend(audio_response.content)
                        else:
                            print(f"[WARNING] Failed to download {section_name} chunk audio")
            
            if not all_audio_data:
                return jsonify({
                    'status': 'success',
                    'script': podcast_script,
                    'audio_url': None,
                    'warning': 'Failed to generate audio'
                })
            
            # Save the combined audio file
            with open(audio_path, 'wb') as f:
                f.write(all_audio_data)
            
            audio_url = f"/static/audio/{audio_filename}"
            print(f"[INFO] Successfully saved audio to {audio_path}")
            
        except Exception as e:
            print(f"[ERROR] Error generating audio: {str(e)}")
            import traceback
            traceback.print_exc()
        
        return jsonify({
            'status': 'success',
            'script': podcast_script,
            'audio_url': audio_url
        })
        
    except Exception as e:
        print(f"An unexpected error occurred in generate_podcast: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": "An internal server error occurred."}), 500

if __name__ == '__main__':
    # Create the uploads and static/audio directories if they don't exist
    os.makedirs('uploads', exist_ok=True)
    os.makedirs('static/audio', exist_ok=True)
    app.run(debug=True, port=5000)
