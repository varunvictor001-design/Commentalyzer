from __future__ import annotations

import json
import os
import re
import traceback
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

try:
    from .config import (
        YOUTUBE_API_KEY,
        DEFAULT_VIDEOS,
        DEFAULT_COMMENTS_PER_VIDEO,
        MAX_VIDEOS,
        MAX_COMMENTS_PER_VIDEO,
        DEMO_MODE,
    )
except ImportError:
    from config import (
        YOUTUBE_API_KEY,
        DEFAULT_VIDEOS,
        DEFAULT_COMMENTS_PER_VIDEO,
        MAX_VIDEOS,
        MAX_COMMENTS_PER_VIDEO,
        DEMO_MODE,
    )

try:
    from .pipeline import (
        Post,
        AnalysisResult,
        YouTubeIngestion,
        TextCleaner,
        LanguageDetector,
        SentimentAnalyzer,
        EmotionAnalyzer,
        IssueAnalyzer,
        ClaimExtractor,
        ClaimVerifier,
        TrendAnalyzer,
    )
except ImportError:
    from pipeline import (
        Post,
        AnalysisResult,
        YouTubeIngestion,
        TextCleaner,
        LanguageDetector,
        SentimentAnalyzer,
        EmotionAnalyzer,
        IssueAnalyzer,
        ClaimExtractor,
        ClaimVerifier,
        TrendAnalyzer,
    )

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR.parent / "frontend"

app = Flask(__name__, static_folder=str(FRONTEND_DIR), static_url_path="")
CORS(app)


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------

def clean_configured_key() -> str:
    # Environment variable wins, which makes deployment easier, while the
    # requested code-based config remains the default.
    return (os.getenv("YOUTUBE_API_KEY") or YOUTUBE_API_KEY or "").strip()


def post_to_dict(result: AnalysisResult) -> dict:
    p = result.post
    return {
        "id": p.post_id,
        "text": p.text,
        "cleaned_text": p.cleaned_text,
        "platform": p.platform,
        "language": p.language,
        "timestamp": p.timestamp,
        "likes": p.likes,
        "replies": p.replies,
        "video_id": p.video_id,
        "video_title": p.video_title,
        "video_url": p.video_url,
        "author": p.author,
        "spam": p.is_spam,
        "sentiment": result.sentiment,
        "emotion": result.emotion,
        "claims": result.verdicts,
    }


def parse_int(value, default, minimum=1, maximum=None):
    try:
        n = int(value)
    except (TypeError, ValueError):
        n = default
    n = max(minimum, n)
    if maximum is not None:
        n = min(maximum, n)
    return n


def issue_rows(issue_counts: Counter, usable_total: int) -> list[dict]:
    rows = []
    for issue, count in issue_counts.most_common(8):
        pct = (count * 100 / usable_total) if usable_total else 0
        severity = "HIGH" if pct >= 30 else "MEDIUM" if pct >= 15 else "LOW"
        rows.append({"issue": issue, "count": count, "percentage": round(pct, 1), "severity": severity})
    return rows


def build_demo_posts(scheme: str) -> list[Post]:
    now = datetime.now(timezone.utc)
    samples = [
        "Applied 3 months ago, still no update on my application. Very frustrating.",
        "Payment received today, thank you government! 🙏",
        "Who can apply? I am confused about eligibility and documents required.",
        "My payment is delayed and money not received yet 😞",
        "The process was smooth and helpful, thank you! 😊",
        "No response from the helpline and my application is still pending.",
        "They are asking for a bribe to process the application.",
        "I finally got the benefit amount, very useful.",
        "Is this scheme fake? I got nothing after applying.",
        "How much benefit does this scheme provide?",
    ]
    posts = []
    for i, text in enumerate(samples):
        dt = now.replace(hour=max(0, 12 - i // 2), minute=0, second=0, microsecond=0)
        posts.append(Post(
            post_id=f"demo-{i+1}", text=text, platform="youtube", scheme=scheme,
            timestamp=dt.isoformat(), video_id=f"demo-video-{i%3+1}",
            video_title=f"{scheme} — demonstration source {i%3+1}",
            video_url=f"https://www.youtube.com/watch?v=demo{i%3+1}", author="Demo user",
            likes=(i + 1) * 3, replies=i % 4,
        ))
    return posts


def run_full_pipeline(posts: list[Post], scheme_name: str) -> dict:
    cleaner = TextCleaner()
    for post in posts:
        cleaner.clean(post)

    deduped = cleaner.dedupe(posts)

    language_detector = LanguageDetector()
    sentiment_analyzer = SentimentAnalyzer()
    emotion_analyzer = EmotionAnalyzer()
    claim_extractor = ClaimExtractor()
    claim_verifier = ClaimVerifier()

    results: list[AnalysisResult] = []
    for post in deduped:
        text = post.cleaned_text or post.text
        post.language = language_detector.detect(text)
        sentiment = sentiment_analyzer.analyze(text, post.emoji_signal)
        emotion = emotion_analyzer.analyze(text, post.emoji_signal)
        claims = claim_extractor.extract(text)
        verdicts = [claim_verifier.verify(c, scheme_name) for c in claims]
        results.append(AnalysisResult(post=post, sentiment=sentiment, emotion=emotion, claims=claims, verdicts=verdicts))

    usable = [r for r in results if not r.post.is_spam]
    sentiment_counts = Counter(r.sentiment for r in usable)
    emotion_counts = Counter(r.emotion for r in usable)
    issues = IssueAnalyzer().analyze([r.post for r in usable])

    negative_posts = [r.post for r in usable if r.sentiment == "Negative"]
    volume = TrendAnalyzer.complaint_volume(negative_posts)
    growth = TrendAnalyzer.growth_percentage(volume)

    all_verdicts = [v for r in usable for v in r.verdicts]
    verdict_counts = Counter(v.get("verdict", "UNVERIFIED") for v in all_verdicts)

    total = len(usable)
    def pct(k):
        return round(sentiment_counts.get(k, 0) * 100 / total, 1) if total else 0.0

    return {
        "scheme": scheme_name,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "raw": len(posts),
        "deduplicated": len(deduped),
        "filtered": len(results) - len(usable),
        "total": total,
        "videos": [],
        "sentiment": {
            "Positive": pct("Positive"),
            "Neutral": pct("Neutral"),
            "Negative": pct("Negative"),
        },
        "sentiment_counts": dict(sentiment_counts),
        "emotions": dict(emotion_counts),
        "issues": issue_rows(issues, total),
        "claims": {
            "total": len(all_verdicts),
            "supported": verdict_counts.get("SUPPORTED", 0),
            "contradicted": verdict_counts.get("CONTRADICTED", 0),
            "unverified": verdict_counts.get("UNVERIFIED", 0),
        },
        "trend": {
            "growth": growth,
            "direction": "up" if growth > 0 else "down" if growth < 0 else "stable",
            "volume": [{"date": d, "count": c} for d, c in volume.items()],
        },
        "comments": [post_to_dict(r) for r in usable],
        "all_comments": [post_to_dict(r) for r in results],
        "claim_rows": all_verdicts[:100],
    }


# ------------------------------------------------------------
# Routes
# ------------------------------------------------------------

@app.get("/api/health")
def health():
    key = clean_configured_key()
    configured = bool(key and "PASTE_YOUR" not in key.upper())
    return jsonify({
        "ok": True,
        "service": "SIH 2026 Government Scheme Intelligence Backend",
        "youtube_configured": configured,
        "demo_mode": bool(DEMO_MODE),
    })


@app.post("/api/analyze")
def analyze():
    payload = request.get_json(silent=True) or {}
    scheme = str(payload.get("scheme", "")).strip()
    if not scheme:
        return jsonify({"error": "Scheme name is required."}), 400

    videos_limit = parse_int(payload.get("videos"), DEFAULT_VIDEOS, 1, MAX_VIDEOS)
    comments_limit = parse_int(payload.get("comments"), DEFAULT_COMMENTS_PER_VIDEO, 1, MAX_COMMENTS_PER_VIDEO)

    try:
        if DEMO_MODE:
            posts = build_demo_posts(scheme)
            videos = [
                {"video_id": f"demo-video-{i}", "title": f"{scheme} — demonstration source {i}",
                 "description": "Demo source", "channel": "SIH Demo", "published_at": datetime.now(timezone.utc).isoformat(),
                 "url": f"https://www.youtube.com/watch?v=demo{i}"}
                for i in range(1, 4)
            ]
        else:
            api_key = clean_configured_key()
            if not api_key or "PASTE_YOUR" in api_key.upper():
                return jsonify({
                    "error": "YouTube API key is not configured. Put your key in backend/config.py (YOUTUBE_API_KEY) and restart the backend."
                }), 503
            ingestion = YouTubeIngestion(api_key)
            videos = ingestion.search_videos(scheme, videos_limit)
            posts = ingestion.collect_comments_from_videos(videos, scheme, comments_limit)

        result = run_full_pipeline(posts, scheme)
        result["videos"] = videos
        result["video_count"] = len(videos)
        result["collection"] = {
            "videos_requested": videos_limit,
            "videos_found": len(videos),
            "comments_per_video_requested": comments_limit,
            "comments_collected": len(posts),
        }
        return jsonify(result)

    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc) or "Analysis failed."}), 500


@app.get("/")
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.get("/<path:path>")
def static_files(path):
    return send_from_directory(FRONTEND_DIR, path)


if __name__ == "__main__":
    print("SIH 2026 backend running at http://127.0.0.1:5501")
    print("Open http://127.0.0.1:5501 in your browser")
    app.run(host="127.0.0.1", port=5501, debug=False)
