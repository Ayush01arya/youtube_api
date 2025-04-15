from flask import Flask, request, jsonify
from pytube import YouTube
from youtube_transcript_api import YouTubeTranscriptApi
import logging

# Initialize Flask app
app = Flask(__name__)

# Set up logging
logging.basicConfig(level=logging.DEBUG)


@app.route("/extract", methods=["POST"])
def extract_metadata():
    # Get JSON data from request
    data = request.json

    # Check if data exists and youtube_url is provided
    if not data or not data.get("youtube_url"):
        app.logger.error("Invalid request: 'youtube_url' is missing")
        return jsonify({"error": "'youtube_url' is required"}), 400

    youtube_url = data.get("youtube_url")
    app.logger.info(f"Received YouTube URL: {youtube_url}")

    try:
        # Initialize YouTube object
        yt = YouTube(youtube_url)
        video_id = yt.video_id

        # Get metadata
        metadata = {
            "title": yt.title,
            "channel_name": yt.author,
            "description": yt.description,
            "publish_date": str(yt.publish_date),
            "view_count": yt.views,
            "duration_seconds": yt.length,
            "video_url": youtube_url
        }

        # Attempt to get transcript
        try:
            transcript_data = YouTubeTranscriptApi.get_transcript(video_id)
            transcript_text = " ".join([item['text'] for item in transcript_data])
        except Exception as e:
            app.logger.error(f"Error fetching transcript: {e}")
            transcript_text = "Transcript not available."

        # Prepare final result
        result = {
            "metadata": metadata,
            "transcript": transcript_text
        }

        return jsonify(result)

    except Exception as e:
        app.logger.error(f"Error extracting video data: {e}")
        return jsonify({"error": str(e)}), 400


if __name__ == "__main__":
    app.run(debug=True)
