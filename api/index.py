from flask import Flask, request, jsonify
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound, VideoUnavailable
from pytube import YouTube
from flask_cors import CORS
from urllib.parse import urlparse, parse_qs

app = Flask(__name__)
CORS(app)

@app.route('/get_youtube_data', methods=['POST'])
def get_youtube_data():
    try:
        data = request.get_json()
        video_url = data.get("video_url")

        if not video_url:
            return jsonify({"error": "Missing video_url in request"}), 400

        video_id = extract_video_id(video_url)

        yt = YouTube(video_url)
        metadata = {
            "title": yt.title,
            "channel_name": yt.author,
            "view_count": yt.views,
            "publish_date": yt.publish_date.isoformat(),
            "description": yt.description,
            "duration_seconds": yt.length,
            "video_url": video_url,
            "video_id": video_id
        }

        try:
            transcript_data = YouTubeTranscriptApi.get_transcript(video_id)
            transcript = " ".join([entry['text'] for entry in transcript_data])
        except (TranscriptsDisabled, NoTranscriptFound):
            transcript = "Transcript not available for this video."
        except VideoUnavailable:
            transcript = "The video is unavailable or restricted."
        except Exception as e:
            transcript = f"Could not fetch transcript: {str(e)}"

        return jsonify({"metadata": metadata, "transcript": transcript})
    
    except Exception as e:
        return jsonify({"error": f"Server Error: {str(e)}"}), 500

def extract_video_id(video_url):
    query = urlparse(video_url)
    if query.hostname in ['www.youtube.com', 'youtube.com']:
        return parse_qs(query.query).get('v', [None])[0]
    elif query.hostname == 'youtu.be':
        return query.path[1:]
    return None

if __name__ == '__main__':
    app.run(debug=True)
