"""Fetch YouTube transcripts (youtube-transcript-api >= 1.0)."""
from youtube_transcript_api import YouTubeTranscriptApi

PREFERRED = ["en", "en-US", "en-GB", "hi"]

FRIENDLY = {
    "TranscriptsDisabled": "Captions are turned off for this video.",
    "NoTranscriptFound": "No transcript was found for this video.",
    "VideoUnavailable": "This video is unavailable (private, removed or region-blocked).",
    "VideoUnplayable": "This video can't be played, so its transcript can't be read.",
    "AgeRestricted": "Age-restricted videos can't be read without signing in.",
    "InvalidVideoId": "That isn't a valid YouTube video ID.",
    "IpBlocked": "YouTube is blocking this network. Try another network or a proxy.",
    "RequestBlocked": "YouTube is blocking this network. Try another network or a proxy.",
}


class TranscriptError(Exception):
    """Raised with a user-friendly message."""


def get_transcript(video_id: str) -> list:
    """Return a list of {'text', 'start', 'duration'} dicts."""
    api = YouTubeTranscriptApi()
    try:
        try:
            fetched = api.fetch(video_id, languages=PREFERRED)
        except Exception as e:
            if type(e).__name__ != "NoTranscriptFound":
                raise
            # No English/Hindi captions: use whatever language exists
            fetched = next(iter(api.list(video_id))).fetch()
        return fetched.to_raw_data()
    except Exception as e:
        msg = FRIENDLY.get(type(e).__name__, f"Could not fetch the transcript: {e}")
        raise TranscriptError(msg) from e
