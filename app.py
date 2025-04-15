from flask import Flask, request, jsonify
from pytube import YouTube
from youtube_transcript_api import YouTubeTranscriptApi

app = Flask(__name__)


@app.route("/extract", methods=["POST"])
def extract_metadata():
    data = request.json
    youtube_url = data.get("youtube_url")

    try:
        yt = YouTube(youtube_url)
        video_id = yt.video_id

        metadata = {
            "title": yt.title,
            "channel_name": yt.author,
            "description": yt.description,
            "publish_date": str(yt.publish_date),
            "view_count": yt.views,
            "duration_seconds": yt.length,
            "video_url": youtube_url
        }

        try:
            transcript_data = YouTubeTranscriptApi.get_transcript(video_id)
            transcript_text = " ".join([item['text'] for item in transcript_data])
        except:
            transcript_text = "Transcript not available."

        result = {
            "metadata": metadata,
            "transcript": transcript_text
        }

        return jsonify(result)

    except Exception as e:
        return jsonify({"error": str(e)}), 400


if __name__ == "__main__":
    app.run(debug=True)
