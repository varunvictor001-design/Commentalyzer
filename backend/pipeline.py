"""
SIH26152 — Social Media Analytics for Government Schemes
=========================================================

REAL YOUTUBE VERSION

Pipeline:
    User enters scheme name
            ↓
    YouTube video search
            ↓
    YouTube comment collection
            ↓
    Text cleaning / deduplication / spam detection
            ↓
    Sentiment analysis
            ↓
    Emotion analysis
            ↓
    Major issue extraction
            ↓
    Claim extraction
            ↓
    Claim verification
            ↓
    Trend / complaint growth
            ↓
    Government Intelligence Dashboard

Requirements:
    pip install google-api-python-client

Set your API key:
    Windows PowerShell:
        $env:YOUTUBE_API_KEY="YOUR_API_KEY"

    Linux/macOS:
        export YOUTUBE_API_KEY="YOUR_API_KEY"

Run:
    python main.py

IMPORTANT:
    This prototype uses the YouTube Data API rather than scraping
    YouTube's rendered HTML pages.
"""

import os
import re
import json
import math
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone


# ============================================================
# 0. DATA MODEL
# ============================================================

@dataclass
class Post:
    post_id: str
    text: str
    platform: str = "youtube"
    language: str = ""
    scheme: str = ""
    timestamp: str = ""
    likes: int = 0
    shares: int = 0
    replies: int = 0
    video_id: str = ""
    video_title: str = ""
    video_url: str = ""
    author: str = ""
    emoji_signal: str = ""
    is_spam: bool = False
    cleaned_text: str = ""


@dataclass
class AnalysisResult:
    post: Post
    sentiment: str = "Neutral"
    emotion: str = "neutral"
    claims: list = field(default_factory=list)
    verdicts: list = field(default_factory=list)


# ============================================================
# 1. YOUTUBE DATA INGESTION
# ============================================================

class YouTubeIngestion:

    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError(
                "YouTube API key missing. "
                "Set the YOUTUBE_API_KEY environment variable."
            )

        try:
            from googleapiclient.discovery import build
        except ImportError:
            raise ImportError(
                "google-api-python-client is not installed.\n"
                "Run: pip install google-api-python-client"
            )

        self.youtube = build(
            "youtube",
            "v3",
            developerKey=api_key
        )

    # --------------------------------------------------------
    # Search videos
    # --------------------------------------------------------

    def search_videos(
        self,
        scheme_name: str,
        max_videos: int = 10
    ) -> list:

        print(f"\n🔎 Searching YouTube for: {scheme_name}")

        request = self.youtube.search().list(
            part="snippet",
            q=scheme_name,
            type="video",
            maxResults=max_videos,
            order="relevance"
        )

        response = request.execute()

        videos = []

        for item in response.get("items", []):

            video_id = item["id"]["videoId"]

            videos.append({
                "video_id": video_id,
                "title": item["snippet"]["title"],
                "description": item["snippet"].get("description", ""),
                "channel": item["snippet"]["channelTitle"],
                "published_at": item["snippet"]["publishedAt"],
                "url": f"https://www.youtube.com/watch?v={video_id}"
            })

        print(f"✓ Found {len(videos)} relevant videos")

        return videos

    # --------------------------------------------------------
    # Collect comments
    # --------------------------------------------------------

    def get_comments(
        self,
        video,
        scheme_name: str,
        max_comments: int = 100
    ) -> list:

        comments = []

        video_id = video["video_id"]

        try:

            request = self.youtube.commentThreads().list(
                part="snippet",
                videoId=video_id,
                maxResults=min(100, max_comments),
                textFormat="plainText",
                order="relevance"
            )

            while request and len(comments) < max_comments:

                response = request.execute()

                for item in response.get("items", []):

                    try:
                        top_comment = (
                            item["snippet"]
                            ["topLevelComment"]
                            ["snippet"]
                        )

                        text = top_comment.get(
                            "textDisplay",
                            ""
                        )

                        if not text.strip():
                            continue

                        published = top_comment.get(
                            "publishedAt",
                            ""
                        )

                        likes = top_comment.get(
                            "likeCount",
                            0
                        )

                        replies = item["snippet"].get(
                            "totalReplyCount",
                            0
                        )

                        comment_id = (
                            item["snippet"]
                            ["topLevelComment"]
                            ["id"]
                        )

                        comments.append(
                            Post(
                                post_id=comment_id,
                                text=text,
                                platform="youtube",
                                scheme=scheme_name,
                                timestamp=published,
                                likes=likes,
                                replies=replies,
                                video_id=video_id,
                                video_title=video["title"],
                                video_url=video["url"],
                                author=top_comment.get(
                                    "authorDisplayName",
                                    ""
                                )
                            )
                        )

                        if len(comments) >= max_comments:
                            break

                    except KeyError:
                        continue

                next_token = response.get(
                    "nextPageToken"
                )

                if not next_token:
                    break

                request = self.youtube.commentThreads().list(
                    part="snippet",
                    videoId=video_id,
                    maxResults=min(
                        100,
                        max_comments - len(comments)
                    ),
                    pageToken=next_token,
                    textFormat="plainText",
                    order="relevance"
                )

        except Exception as exc:

            print(
                f"⚠ Could not retrieve comments "
                f"for video {video_id}: {exc}"
            )

        return comments

    # --------------------------------------------------------
    # Complete collection
    # --------------------------------------------------------

    def collect_comments_from_videos(
        self,
        videos: list,
        scheme_name: str,
        comments_per_video: int = 100
    ) -> list:

        all_comments = []

        for index, video in enumerate(videos, 1):

            print(
                f"  [{index}/{len(videos)}] "
                f"Collecting comments: "
                f"{video['title'][:70]}"
            )

            comments = self.get_comments(
                video,
                scheme_name,
                comments_per_video
            )

            all_comments.extend(comments)

        print(
            f"\n✓ Total comments collected: "
            f"{len(all_comments)}"
        )

        return all_comments


# ============================================================
# 2. TEXT CLEANING
# ============================================================

class TextCleaner:

    EMOJI_MAP = {
        "😡": "anger",
        "🤬": "anger",
        "😠": "anger",
        "😟": "fear",
        "😨": "fear",
        "😰": "fear",
        "😕": "confusion",
        "🤔": "confusion",
        "🙏": "gratitude",
        "😊": "joy",
        "👍": "joy",
        "👏": "joy",
        "💔": "disappointment",
        "😞": "disappointment",
        "😤": "frustration",
        "😫": "frustration",
    }

    URL_RE = re.compile(
        r"https?://\S+|www\.\S+"
    )

    SPAM_HINTS = [
        "click here",
        "free ",
        "offer",
        "lottery",
        "whatsapp group",
        "dm me",
        "subscribe to my channel",
        "earn money",
        "visit my channel"
    ]

    def clean(self, post: Post):

        text = post.text

        # Preserve emoji as emotion signal
        signals = [
            self.EMOJI_MAP[c]
            for c in text
            if c in self.EMOJI_MAP
        ]

        post.emoji_signal = (
            signals[0] if signals else ""
        )

        # Remove URLs
        text = self.URL_RE.sub("", text)

        # Remove excessive whitespace
        text = re.sub(
            r"\s+",
            " ",
            text
        ).strip()

        post.cleaned_text = text

        low = text.lower()

        # Spam flag
        if (
            any(h in low for h in self.SPAM_HINTS)
            or len(text) < 8
        ):
            post.is_spam = True

        return post

    @staticmethod
    def dedupe(posts):

        seen = set()
        output = []

        for post in posts:

            normalized = re.sub(
                r"\W+",
                "",
                post.cleaned_text.lower()
            )

            if not normalized:
                continue

            if normalized in seen:
                continue

            seen.add(normalized)
            output.append(post)

        return output


# ============================================================
# 3. LANGUAGE DETECTION
# ============================================================

class LanguageDetector:

    TRANSLIT = {
        "yaar",
        "bhai",
        "kya",
        "paisa",
        "bakwas",
        "nahi",
        "deta",
        "jhansa",
        "kaise",
        "milega",
        "sach",
        "sirf",
        "hai",
        "nahi",
        "kyun",
        "kab"
    }

    @staticmethod
    def detect(text):

        counts = {
            "devanagari": 0,
            "tamil": 0,
            "latin": 0
        }

        for char in text:

            code = ord(char)

            if 0x0900 <= code <= 0x097F:
                counts["devanagari"] += 1

            elif 0x0B80 <= code <= 0x0BFF:
                counts["tamil"] += 1

            elif char.isalpha():
                counts["latin"] += 1

        words = set(
            re.findall(
                r"[a-z]+",
                text.lower()
            )
        )

        translit_hits = len(
            words & LanguageDetector.TRANSLIT
        )

        if (
            counts["devanagari"]
            and counts["latin"] > 2
        ):
            return "Code-mixed"

        if (
            counts["tamil"]
            and counts["latin"] > 2
        ):
            return "Code-mixed"

        if counts["devanagari"]:
            return "Hindi"

        if counts["tamil"]:
            return "Tamil"

        if translit_hits >= 2:
            return "Code-mixed"

        return "English"


# ============================================================
# 4. SENTIMENT ANALYSIS
# ============================================================

class SentimentAnalyzer:

    POSITIVE = {
        "thank": 2,
        "thanks": 2,
        "good": 2,
        "great": 2,
        "excellent": 3,
        "amazing": 3,
        "helpful": 2,
        "useful": 2,
        "lifesaver": 3,
        "smooth": 2,
        "received": 1,
        "success": 2,
        "benefit": 1,
        "happy": 2,
        "dhanyavad": 2,
        "shukriya": 2,
        "accha": 2,
        "nalla": 2,
        "நன்றி": 2,
        "நல்லா": 2,
        "मुफ्त": 1,
    }

    NEGATIVE = {
        "fake": 3,
        "fraud": 3,
        "scam": 3,
        "bakwas": 3,
        "jhansa": 3,
        "nothing": 2,
        "not received": 3,
        "haven't received": 3,
        "no payment": 3,
        "delay": 2,
        "delayed": 2,
        "waiting": 2,
        "frustrating": 3,
        "frustrated": 3,
        "disappointed": 3,
        "rejected": 2,
        "problem": 2,
        "issue": 2,
        "complaint": 2,
        "harassment": 3,
        "bribe": 3,
        "corruption": 3,
        "nahi": 1,
        "கிடைக்கவில்லை": 3,
        "ஏமாற்றம்": 3,
        "परेशान": 3,
    }

    def analyze(
        self,
        text,
        emoji_signal=""
    ):

        low = text.lower()

        score = 0

        for word, weight in self.POSITIVE.items():

            if word in low:
                score += weight

        for word, weight in self.NEGATIVE.items():

            if word in low:
                score -= weight

        if emoji_signal in (
            "joy",
            "gratitude"
        ):
            score += 2

        if emoji_signal in (
            "anger",
            "fear",
            "disappointment",
            "frustration"
        ):
            score -= 2

        if score > 0:
            return "Positive"

        if score < 0:
            return "Negative"

        return "Neutral"


# ============================================================
# 5. EMOTION ANALYSIS
# ============================================================

class EmotionAnalyzer:

    SIGNALS = {

        "anger": [
            "fake",
            "fraud",
            "scam",
            "bakwas",
            "harassment",
            "corruption"
        ],

        "frustration": [
            "delay",
            "delayed",
            "still no",
            "waiting",
            "rejected",
            "never picks",
            "problem"
        ],

        "confusion": [
            "confused",
            "kaise",
            "samajh",
            "clarify",
            "kab",
            "eligibility",
            "how to"
        ],

        "satisfaction": [
            "thank",
            "thanks",
            "amazing",
            "received",
            "lifesaver",
            "useful",
            "helpful"
        ],

        "disappointment": [
            "disappointed",
            "nothing",
            "less than promised",
            "not received"
        ],

        "fear": [
            "scared",
            "lost",
            "fear",
            "worried",
            "afraid"
        ]
    }

    def analyze(
        self,
        text,
        emoji_signal=""
    ):

        low = text.lower()

        scores = {}

        for emotion, keywords in self.SIGNALS.items():

            scores[emotion] = sum(
                1
                for keyword in keywords
                if keyword in low
            )

        if emoji_signal in scores:
            scores[emoji_signal] += 1

        if not scores:
            return "neutral"

        best = max(
            scores,
            key=scores.get
        )

        return (
            best
            if scores[best] > 0
            else "neutral"
        )


# ============================================================
# 6. MAJOR ISSUE DETECTION
# ============================================================

class IssueAnalyzer:

    ISSUES = {

        "Application delay": [
            "delay",
            "delayed",
            "waiting",
            "still no update",
            "pending",
            "application pending",
            "months ago",
            "waiting list"
        ],

        "Eligibility confusion": [
            "eligible",
            "eligibility",
            "who can apply",
            "can i apply",
            "criteria",
            "qualification",
            "documents required",
            "confused"
        ],

        "Payment delay": [
            "payment delay",
            "payment delayed",
            "not received",
            "haven't received",
            "no payment",
            "money not received",
            "paisa nahi",
            "amount not received"
        ],

        "Benefit amount confusion": [
            "amount",
            "how much",
            "₹",
            "lakh",
            "benefit",
            "money",
            "deta hai"
        ],

        "Fraud / misinformation": [
            "fake",
            "fraud",
            "scam",
            "jhansa",
            "bakwas",
            "fake scheme"
        ],

        "Corruption / bribe": [
            "bribe",
            "corruption",
            "middleman",
            "commission",
            "₹5000",
            "₹10000"
        ],

        "Application rejection": [
            "rejected",
            "rejection",
            "application rejected",
            "denied"
        ],

        "Grievance / helpline": [
            "helpline",
            "complaint",
            "grievance",
            "call",
            "not picking",
            "no response"
        ]
    }

    def analyze(self, posts):

        counts = Counter()

        for post in posts:

            text = post.cleaned_text.lower()

            for issue, keywords in self.ISSUES.items():

                if any(
                    keyword.lower() in text
                    for keyword in keywords
                ):
                    counts[issue] += 1

        return counts


# ============================================================
# 7. CLAIM EXTRACTION
# ============================================================

class ClaimExtractor:

    PATTERNS = [

        (
            r"₹\s?[\d.,]+\s?(lakh|crore|k)?",
            "BENEFIT_AMOUNT"
        ),

        (
            r"(gives?|deta hai|provides?)\s+.*",
            "ENTITLEMENT_CLAIM"
        ),

        (
            r"\b(fake|scam|fraud|bakwas|jhansa)\b",
            "FRAUD_ALLEGATION"
        ),

        (
            r"payment received|paisa aa gaya|வந்தது|मिल गया",
            "PAYMENT_RECEIVED"
        ),

        (
            r"got nothing|नहीं मिल|கிடைக்கவில்லை|no update|not received|haven't received",
            "PAYMENT_NOT_RECEIVED"
        ),

        (
            r"demanding ₹?\d+ bribe|bribe",
            "CORRUPTION_ALLEGATION"
        )
    ]

    def extract(self, text):

        claims = []

        for pattern, claim_type in self.PATTERNS:

            matches = re.finditer(
                pattern,
                text,
                re.IGNORECASE
            )

            for match in matches:

                claims.append({
                    "type": claim_type,
                    "text": match.group(0).strip()
                })

        return claims


# ============================================================
# 8. SIMPLE CLAIM VERIFICATION
# ============================================================

class ClaimVerifier:

    """
    Prototype verifier.

    IMPORTANT:
    For SIH production, replace this with:
        Government documents
             ↓
        embeddings
             ↓
        vector database
             ↓
        RAG retrieval
             ↓
        LLM verification
    """

    KNOWLEDGE_BASE = {

        "housing": [
            "Housing scheme benefits depend on eligibility and scheme guidelines."
        ],

        "pmay": [
            "PMAY benefits are provided to eligible beneficiaries according to official scheme guidelines."
        ],

        "pension": [
            "Pension benefits depend on state and scheme eligibility."
        ],

        "farmer": [
            "Farmer scheme payments are provided to eligible beneficiaries according to official guidelines."
        ],

        "health": [
            "Health scheme coverage depends on the eligibility and official scheme guidelines."
        ]
    }

    def verify(
        self,
        claim,
        scheme_name
    ):

        text = (
            claim["text"]
            + " "
            + scheme_name
        ).lower()

        # No evidence
        evidence = None

        for key, facts in self.KNOWLEDGE_BASE.items():

            if key in text:

                evidence = facts[0]
                break

        if not evidence:

            return {
                "claim": claim["text"],
                "type": claim["type"],
                "verdict": "UNVERIFIED",
                "evidence": "",
                "source": "No government evidence configured"
            }

        # Fraud claims should not automatically be called false.
        # We classify them as unverified unless official evidence
        # is available to contradict the allegation.
        if claim["type"] == "FRAUD_ALLEGATION":

            return {
                "claim": claim["text"],
                "type": claim["type"],
                "verdict": "UNVERIFIED",
                "evidence": evidence,
                "source": "Prototype knowledge base"
            }

        return {
            "claim": claim["text"],
            "type": claim["type"],
            "verdict": "SUPPORTED",
            "evidence": evidence,
            "source": "Prototype knowledge base"
        }


# ============================================================
# 9. TREND ANALYSIS
# ============================================================

class TrendAnalyzer:

    @staticmethod
    def complaint_volume(posts):

        volume = defaultdict(int)

        for post in posts:

            if post.is_spam:
                continue

            if not post.timestamp:
                continue

            # Convert YouTube timestamp to date
            try:

                dt = datetime.fromisoformat(
                    post.timestamp.replace(
                        "Z",
                        "+00:00"
                    )
                )

                day = dt.date().isoformat()

            except Exception:

                day = post.timestamp[:10]

            volume[day] += 1

        return dict(
            sorted(volume.items())
        )

    @staticmethod
    def growth_percentage(volume):

        if len(volume) < 2:
            return 0.0

        days = list(volume.values())

        recent = days[-1]

        previous = days[:-1]

        baseline = (
            sum(previous)
            / len(previous)
        )

        if baseline == 0:
            return 0.0

        growth = (
            (recent - baseline)
            / baseline
        ) * 100

        return round(growth, 1)


# ============================================================
# 10. MAIN ANALYSIS PIPELINE
# ============================================================

def run_pipeline(
    posts,
    scheme_name
):

    cleaner = TextCleaner()

    # ------------------------------------------
    # CLEAN
    # ------------------------------------------

    for post in posts:
        cleaner.clean(post)

    # ------------------------------------------
    # DEDUPLICATE
    # ------------------------------------------

    posts = cleaner.dedupe(posts)

    # ------------------------------------------
    # FILTER / ANALYSE
    # ------------------------------------------

    language_detector = LanguageDetector()
    sentiment_analyzer = SentimentAnalyzer()
    emotion_analyzer = EmotionAnalyzer()
    claim_extractor = ClaimExtractor()
    claim_verifier = ClaimVerifier()

    results = []

    for post in posts:

        text = (
            post.cleaned_text
            or post.text
        )

        post.language = (
            language_detector.detect(text)
        )

        sentiment = sentiment_analyzer.analyze(
            text,
            post.emoji_signal
        )

        emotion = emotion_analyzer.analyze(
            text,
            post.emoji_signal
        )

        claims = claim_extractor.extract(
            text
        )

        verdicts = [
            claim_verifier.verify(
                claim,
                scheme_name
            )
            for claim in claims
        ]

        results.append(
            AnalysisResult(
                post=post,
                sentiment=sentiment,
                emotion=emotion,
                claims=claims,
                verdicts=verdicts
            )
        )

    return results


# ============================================================
# 11. DASHBOARD
# ============================================================

def print_dashboard(
    scheme_name,
    results,
    issues,
    volume,
    growth,
    videos_count
):

    total = len(results)

    if total == 0:

        print(
            "\n❌ No usable comments found."
        )

        return

    sentiment = Counter(
        r.sentiment
        for r in results
    )

    all_verdicts = []

    for result in results:
        all_verdicts.extend(
            result.verdicts
        )

    verdict_counts = Counter(
        v["verdict"]
        for v in all_verdicts
    )

    positive = (
        sentiment["Positive"]
        * 100
        / total
    )

    neutral = (
        sentiment["Neutral"]
        * 100
        / total
    )

    negative = (
        sentiment["Negative"]
        * 100
        / total
    )

    print("\n")
    print("=" * 70)

    print(
        f"SCHEME: {scheme_name}"
    )

    print("=" * 70)

    print(
        f"\nYouTube Videos Analysed: "
        f"{videos_count}"
    )

    print(
        f"Comments Analysed: {total}"
    )

    print("\nPublic Sentiment")
    print("────────────────────────")

    print(
        f"Positive       {positive:.1f}%"
    )

    print(
        f"Neutral        {neutral:.1f}%"
    )

    print(
        f"Negative       {negative:.1f}%"
    )

    # ------------------------------------------
    # MAJOR ISSUES
    # ------------------------------------------

    print("\nMajor Issues")
    print("────────────────────────")

    if issues:

        top_issues = issues.most_common(5)

        for index, (issue, count) in enumerate(
            top_issues,
            1
        ):

            percentage = (
                count * 100 / total
            )

            if percentage >= 30:
                icon = "🔴"

            elif percentage >= 15:
                icon = "🟠"

            else:
                icon = "🟡"

            print(
                f"{index}. "
                f"{issue:<25} "
                f"{icon} "
                f"({count})"
            )

    else:

        print(
            "No major recurring issues detected."
        )

    # ------------------------------------------
    # CLAIMS
    # ------------------------------------------

    print("\nClaims Detected")
    print("────────────────────────")

    print(
        f"{len(all_verdicts)} claims"
    )

    print()

    print(
        f"Supported       "
        f"{verdict_counts['SUPPORTED']}"
    )

    print(
        f"Contradicted    "
        f"{verdict_counts['CONTRADICTED']}"
    )

    print(
        f"Unverified      "
        f"{verdict_counts['UNVERIFIED']}"
    )

    # ------------------------------------------
    # TREND
    # ------------------------------------------

    print("\nTrend")
    print("────────────────────────")

    if growth > 0:

        print(
            f"⚠ Complaint volume ↑ "
            f"{growth:.1f}%"
        )

    elif growth < 0:

        print(
            f"✓ Complaint volume ↓ "
            f"{abs(growth):.1f}%"
        )

    else:

        print(
            "Complaint volume → Stable"
        )

    # ------------------------------------------
    # DAILY VOLUME
    # ------------------------------------------

    print("\nDaily Complaint Volume")
    print("────────────────────────")

    for day, count in volume.items():

        print(
            f"{day}  "
            f"{'█' * min(count, 60)} "
            f"{count}"
        )

    print("\n" + "=" * 70)


# ============================================================
# 12. SAVE RESULTS
# ============================================================

def save_json(
    scheme_name,
    results,
    filename="youtube_analysis.json"
):

    data = {

        "scheme": scheme_name,

        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),

        "comments": [

            {
                "id": r.post.post_id,
                "text": r.post.text,
                "cleaned_text": r.post.cleaned_text,
                "language": r.post.language,
                "sentiment": r.sentiment,
                "emotion": r.emotion,
                "likes": r.post.likes,
                "replies": r.post.replies,
                "video_id": r.post.video_id,
                "video_title": r.post.video_title,
                "video_url": r.post.video_url,
                "claims": r.verdicts,
                "spam": r.post.is_spam
            }

            for r in results
        ]
    }

    with open(
        filename,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=2
        )

    print(
        f"\n✓ Results saved to {filename}"
    )


