# YouTube Notes Extractor

Paste a YouTube URL and get a TL;DR, key points, detailed notes, tips, shortcuts, key terms and action items. Built with Streamlit and the Gemini API. Videos of any length work: long transcripts are split into parts, noted separately, then merged.

## Setup
```bash
python -m venv venv
venv\Scripts\activate          # Mac/Linux: source venv/bin/activate
pip install -r requirements.txt
copy .env.example .env         # Mac/Linux: cp .env.example .env
```
Put your Gemini key in `.env`, then run:
```bash
streamlit run app.py
```

## Files
- `app.py`: Streamlit UI
- `transcript.py`: transcript fetching and friendly errors
- `notes_generator.py`: Gemini prompts, chunking, merge
- `utils.py`: URL parsing, metadata, helpers
- `pdf_export.py`: PDF export of the notes
