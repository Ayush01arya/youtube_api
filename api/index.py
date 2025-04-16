from flask import Flask, request, jsonify
from flask_cors import CORS
from youtube_transcript_api import (
    YouTubeTranscriptApi,
    TranscriptsDisabled,
    NoTranscriptFound,
    VideoUnavailable,
    CouldNotRetrieveTranscript,
)
from pytube import YouTube
import re

app = Flask(__name__)
CORS(app)

@app.route("/")
def home():
    return "YouTube Transcript + Metadata API is running."

@app.route("/get_youtube_data", methods=["POST"])
def get_youtube_data():
    try:
        data = request.get_json()
        video_url = data.get("video_url")

        if not video_url:
            return jsonify({"error": "No video URL provided."}), 400

        # Extract video ID from the URL
        match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11})", video_url)
        if not match:
            return jsonify({"error": "Invalid YouTube URL."}), 400
        video_id = match.group(1)

        # Fetch video metadata using pytube
        yt = YouTube(video_url)
        metadata = {
            "title": yt.title,
            "channel_name": yt.author,
            "view_count": yt.views,
            "publish_date": yt.publish_date.isoformat() if yt.publish_date else None,
            "description": yt.description,
            "duration_seconds": yt.length,
            "video_url": video_url,
            "video_id": video_id
        }

        # Try fetching transcript
        try:
            transcripts = YouTubeTranscriptApi.list_transcripts(video_id)
            transcript = transcripts.find_transcript(['en', 'en-US', 'en-GB'])
            transcript_data = transcript.fetch()
            transcript_text = " ".join([entry['text'] for entry in transcript_data])
        except TranscriptsDisabled:
            transcript_text = "Transcript disabled by the video owner."
        except NoTranscriptFound:
            transcript_text = "Transcript not found for this video."
        except VideoUnavailable:
            transcript_text = "Video is unavailable."
        except CouldNotRetrieveTranscript:
            transcript_text = "Could not retrieve transcript. Possibly due to restrictions."
        except Exception as e:
            transcript_text = f"Transcript not available. Error: {str(e)}"

        return jsonify({
            "metadata": metadata,
            "transcript": transcript_text
        })

    except Exception as e:
        return jsonify({"error": f"Internal Server Error: {str(e)}"}), 500

if __name__ == "__main__":
    app.run(debug=True)
