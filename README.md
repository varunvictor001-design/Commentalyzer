# SIH 2026 — Classic Connected Website

This version connects the classic HTML/CSS/JS interface directly to a Flask backend.

## 1. Put the YouTube API key in code

Open:

`backend/config.py`

Set:

```python
YOUTUBE_API_KEY = "YOUR_REAL_YOUTUBE_DATA_API_V3_KEY"
```

The key is **not requested in the GUI**.

For deployment, an environment variable named `YOUTUBE_API_KEY` also overrides the value in `config.py`.

## 2. Install dependencies

Windows:

```bat
py -m venv backend\.venv
backend\.venv\Scripts\activate
pip install -r backend\requirements.txt
```

macOS/Linux:

```bash
python3 -m venv backend/.venv
source backend/.venv/bin/activate
pip install -r backend/requirements.txt
```

## 3. Run

From the project folder:

```bash
python backend/app.py
```

Open:

`http://127.0.0.1:5000`

Or on Windows double-click `start.bat`.

## What happens when ANALYSE SCHEME is clicked

1. Browser sends scheme name + limits to `/api/analyze`.
2. Flask creates the YouTube client using the key in `backend/config.py`.
3. YouTube Data API searches for relevant videos.
4. Comments are collected from each returned video.
5. Comments are cleaned, spam-flagged and deduplicated.
6. Language, sentiment and emotion are analysed.
7. Major issues are extracted.
8. Claims are extracted and checked against the prototype knowledge base.
9. Negative-comment complaint volume is grouped by date and growth is calculated.
10. JSON is returned to the browser and every dashboard panel is populated.

## Important implementation note

The project uses the YouTube Data API rather than scraping YouTube's rendered HTML pages. This is the approach used by the supplied SIH pipeline.

Claim verification is still a prototype knowledge-base verifier. It should not be presented as authoritative fact-checking until it is connected to current official government documents/RAG retrieval.
