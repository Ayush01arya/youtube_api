from flask import Flask, request, jsonify
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
from youtube_transcript_api.formatters import TextFormatter
import logging
from flask_cors import CORS
import re
import traceback
import requests
import os
import isodate
import json
import random
from http_request_randomizer.requests.proxy.requestProxy import RequestProxy

# Initialize Flask app
app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Set up logging
logging.basicConfig(level=logging.DEBUG)

# Initialize proxy manager (only use when needed)
proxy_manager = None

def get_random_proxy():
    """Get a random proxy from the proxy manager"""
    global proxy_manager
    
    try:
        if proxy_manager is None:
            app.logger.info("Initializing proxy manager...")
            proxy_manager = RequestProxy()
        
        proxies = proxy_manager.get_proxy_list()
        if not proxies:
            app.logger.warning("No proxies available")
            return None
        
        proxy = random.choice(proxies)
        proxy_dict = {
            "http": f"http://{proxy.get_address()}",
            "https": f"http://{proxy.get_address()}"
        }
        app.logger.info(f"Using proxy: {proxy.get_address()}")
        return proxy_dict
    except Exception as e:
        app.logger.error(f"Error getting proxy: {e}")
        return None

def extract_video_id(url):
    """Extract the video ID from various YouTube URL formats"""
    youtube_regex = (
        r'(https?://)?(www\.)?'
        '(youtube|youtu|youtube-nocookie)\.(com|be)/'
        '(watch\?v=|embed/|v/|.+\?v=)?([^&=%\?]{11})')

    match = re.match(youtube_regex, url)
    if match:
        return match.group(6)
    return None

def get_transcript(video_id, use_proxy=True):
    """
    Get transcript for a video with proxy support and detailed error handling
    Returns a dictionary with success status, transcript text and error details if any
    """
    try:
        # First attempt without proxy
        try:
            app.logger.info(f"Attempting to get transcript directly for {video_id}")
            transcript_data = YouTubeTranscriptApi.get_transcript(video_id)
            formatter = TextFormatter()
            formatted_transcript = formatter.format_transcript(transcript_data)
            
            return {
                "success": True,
                "transcript_text": formatted_transcript,
                "transcript_type": "direct-api",
                "transcript_details": [{"text": item['text'], "start": item['start'], "duration": item['duration']} for item in transcript_data]
            }
        except Exception as direct_error:
            app.logger.warning(f"Direct transcript fetch failed: {direct_error}")
            
            # If proxy usage is enabled and direct method failed
            if use_proxy:
                app.logger.info("Attempting to get transcript using proxy")
                
                # Try using an alternative method with proxies
                try:
                    # Get lyrics from description as fallback (for music videos)
                    app.logger.info("Checking if lyrics are in video description...")
                    metadata = get_video_metadata(video_id, request.headers.get('X-API-Key'))
                    description = metadata.get("description", "")
                    
                    # Basic check if description contains lyrics
                    if "lyrics" in description.lower() and len(description) > 500:
                        lyrics_section = extract_lyrics_from_description(description)
                        if lyrics_section:
                            return {
                                "success": True,
                                "transcript_text": lyrics_section,
                                "transcript_type": "lyrics-from-description",
                                "transcript_details": [{"text": lyrics_section, "start": 0, "duration": 0}]
                            }
                    
                    # If no lyrics in description, try using proxy for transcript API
                    proxy = get_random_proxy()
                    if proxy:
                        app.logger.info(f"Using proxy: {proxy}")
                        # Note: Currently the YouTube Transcript API doesn't directly support proxies
                        # This is a placeholder for implementing proxy support
                        # You would need to modify the YouTubeTranscriptApi or use a different approach
                        
                        # As a fallback, let's try to fetch from a proxy-friendly alternative
                        # This is where you would implement your proxy solution
                        
                        # Placeholder to show where proxy implementation would go
                        raise NotImplementedError("Proxy support for transcripts requires custom implementation")
                    else:
                        raise Exception("No proxies available")
                        
                except Exception as proxy_error:
                    app.logger.error(f"Proxy method failed: {proxy_error}")
                    raise
            else:
                # Re-raise the original error if proxy not enabled
                raise direct_error

    except TranscriptsDisabled:
        return {
            "success": False,
            "error": "Transcripts are disabled for this video",
            "transcript_text": "Transcript not available: Transcripts are disabled for this video."
        }
    except NoTranscriptFound:
        return {
            "success": False,
            "error": "No transcript found for this video",
            "transcript_text": "Transcript not available: No transcript found for this video."
        }
    except Exception as e:
        # Add specific handling for IP blocking error
        error_str = str(e)
        if "blocked" in error_str.lower() or "ip" in error_str.lower():
            return {
                "success": False,
                "error": "YouTube IP blocking detected. Consider using proxies or cookies as described in the YouTube Transcript API documentation.",
                "transcript_text": f"Transcript not available: YouTube is blocking requests from your IP. Please use a different IP or implement a proxy solution.",
                "alternative_options": [
                    "1. Use a VPN or proxy service",
                    "2. Implement the proxy solution from the YouTube Transcript API documentation",
                    "3. For music videos, extract lyrics from the video description when available"
                ]
            }
        else:
            return {
                "success": False,
                "error": f"Error fetching transcript: {str(e)}",
                "transcript_text": f"Transcript not available: {str(e)}"
            }

def extract_lyrics_from_description(description):
    """Extract lyrics from video description"""
    lines = description.split("\n")
    lyrics_lines = []
    in_lyrics_section = False
    
    # Look for patterns that typically indicate lyrics sections
    for line in lines:
        # Start of lyrics section indicators
        if re.search(r'lyrics:|^lyrics$|^lyrics:$', line.lower().strip()):
            in_lyrics_section = True
            continue
            
        # End of lyrics section indicators (links, hashtags, etc.)
        if in_lyrics_section and (line.startswith("http") or 
                                line.startswith("#") or 
                                "subscribe" in line.lower() or
                                "follow" in line.lower()):
            in_lyrics_section = False
            
        if in_lyrics_section and line.strip():
            lyrics_lines.append(line)
            
    # If we didn't find a clearly marked lyrics section, try another approach
    if not lyrics_lines:
        # Look for verse-like patterns
        verse_pattern = r'(verse|chorus|bridge|hook|outro|intro)[ 0-9]*:?'
        for i, line in enumerate(lines):
            if re.search(verse_pattern, line.lower()):
                # Found a verse marker, extract the following lines
                j = i
                while j < len(lines) and j < i + 20:  # Limit to 20 lines after the marker
                    if lines[j].strip() and not lines[j].startswith("http"):
                        lyrics_lines.append(lines[j])
                    j += 1
    
    # If we still don't have lyrics, look for consecutive short lines that might be lyrics
    if not lyrics_lines:
        consecutive_short_lines = 0
        temp_lyrics = []
        
        for line in lines:
            line = line.strip()
            if line and len(line) < 100 and not line.startswith("http") and "#" not in line:
                consecutive_short_lines += 1
                temp_lyrics.append(line)
            else:
                if consecutive_short_lines >= 4:  # If we found at least 4 consecutive short lines
                    lyrics_lines.extend(temp_lyrics)
                consecutive_short_lines = 0
                temp_lyrics = []
    
    return "\n".join(lyrics_lines) if lyrics_lines else ""

@app.route("/api/extract", methods=["POST", "OPTIONS"])
def extract_metadata():
    # Handle preflight OPTIONS request
    if request.method == "OPTIONS":
        return "", 200

    app.logger.info(f"Request headers: {dict(request.headers)}")
    app.logger.info(f"Request data: {request.data}")

    # Get API key from request header
    api_key = request.headers.get('X-API-Key')
    if not api_key:
        app.logger.error("API key missing from request headers")
        return jsonify({"error": "API key is required in the X-API-Key header"}), 401

    # Get JSON data from request
    try:
        if request.is_json:
            data = request.get_json()
        else:
            app.logger.error("Request is not JSON format")
            return jsonify({"error": "Request must be in JSON format"}), 400
    except Exception as e:
        app.logger.error(f"Error parsing JSON: {e}")
        return jsonify({"error": f"Invalid JSON format: {str(e)}"}), 400

    # Check if data exists and youtube_url is provided
    if not data or not data.get("youtube_url"):
        app.logger.error("Invalid request: 'youtube_url' is missing")
        return jsonify({"error": "'youtube_url' is required"}), 400

    youtube_url = data.get("youtube_url")
    app.logger.info(f"Received YouTube URL: {youtube_url}")
    
    # Check if proxy option is specified
    use_proxy = data.get("use_proxy", True)

    # Extract video ID directly from URL
    video_id = extract_video_id(youtube_url)
    if not video_id:
        return jsonify({"error": "Could not extract valid YouTube video ID"}), 400

    app.logger.info(f"Extracted video ID: {video_id}")

    try:
        # Use YouTube Data API to get video metadata
        metadata = get_video_metadata(video_id, api_key)

        if "error" in metadata:
            return jsonify(metadata), 400

        # Get transcript with detailed error handling
        app.logger.info(f"Fetching transcript for video ID: {video_id}")
        transcript_result = get_transcript(video_id, use_proxy)
        
        # Add transcript info to metadata
        metadata["transcript_available"] = transcript_result["success"]
        if not transcript_result["success"]:
            metadata["transcript_error"] = transcript_result["error"]

        # Prepare final result
        result = {
            "metadata": metadata,
            "transcript": transcript_result["transcript_text"]
        }
        
        # Add detailed transcript info if available
        if transcript_result["success"] and "transcript_details" in transcript_result:
            result["transcript_details"] = transcript_result["transcript_details"]
            result["transcript_type"] = transcript_result["transcript_type"]
        
        # Add alternative options if available
        if "alternative_options" in transcript_result:
            result["alternative_options"] = transcript_result["alternative_options"]

        app.logger.info(f"Final metadata result: {json.dumps(metadata, indent=2)}")
        return jsonify(result)

    except Exception as e:
        app.logger.error(f"Error extracting video data: {e}")
        app.logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 400

def get_video_metadata(video_id, api_key):
    """
    Fetch video metadata using YouTube Data API
    """
    app.logger.info(f"Fetching metadata for video ID: {video_id}")

    try:
        # YouTube Data API v3 endpoint
        api_url = f"https://www.googleapis.com/youtube/v3/videos"

        # Parameters for the API request
        params = {
            "part": "snippet,contentDetails,statistics",
            "id": video_id,
            "key": api_key
        }

        response = requests.get(api_url, params=params)
        response.raise_for_status()  # Raise exception for non-200 status codes

        data = response.json()

        # Check if video data exists
        if not data.get("items"):
            return {"error": "Video not found or not accessible"}

        video_data = data["items"][0]

        # Extract relevant information
        snippet = video_data.get("snippet", {})
        content_details = video_data.get("contentDetails", {})
        statistics = video_data.get("statistics", {})

        # Convert ISO 8601 duration to seconds
        duration_iso = content_details.get("duration", "PT0S")
        duration_seconds = int(isodate.parse_duration(duration_iso).total_seconds())

        # Build metadata object
        metadata = {
            "video_id": video_id,
            "video_url": f"https://www.youtube.com/watch?v={video_id}",
            "title": snippet.get("title", "Title not available"),
            "channel_name": snippet.get("channelTitle", "Channel name not available"),
            "description": snippet.get("description", "Description not available"),
            "publish_date": snippet.get("publishedAt", "Publish date not available"),
            "view_count": int(statistics.get("viewCount", 0)),
            "duration_seconds": duration_seconds
        }

        app.logger.info("Successfully retrieved video metadata")
        return metadata

    except requests.exceptions.RequestException as e:
        app.logger.error(f"Error making request to YouTube API: {e}")
        return {"error": f"YouTube API error: {str(e)}"}
    except (KeyError, ValueError, AttributeError) as e:
        app.logger.error(f"Error parsing YouTube API response: {e}")
        return {"error": f"Error processing YouTube data: {str(e)}"}
    except Exception as e:
        app.logger.error(f"Unexpected error in get_video_metadata: {e}")
        return {"error": f"Error retrieving video metadata: {str(e)}"}

# MindPal Custom API endpoint that follows the MindPal API structure
@app.route("/api/mindpal/extract", methods=["POST"])
def mindpal_extract():
    try:
        # Get API key from request header
        api_key = request.headers.get('X-API-Key')
        if not api_key:
            app.logger.error("API key missing from request headers")
            return jsonify({"success": False, "error": "API key is required in the X-API-Key header"}), 401
        
        # Get JSON data from request
        if request.is_json:
            data = request.get_json()
        else:
            return jsonify({"success": False, "error": "Request must be in JSON format"}), 400
            
        # Check if input data exists
        if not data or not data.get("input"):
            return jsonify({"success": False, "error": "Input field is required"}), 400
            
        # Extract YouTube URL from input
        youtube_url = data.get("input")
        use_proxy = data.get("use_proxy", True)
        
        # Extract video ID
        video_id = extract_video_id(youtube_url)
        if not video_id:
            return jsonify({"success": False, "error": "Could not extract valid YouTube video ID"}), 400
            
        # Get metadata
        metadata = get_video_metadata(video_id, api_key)
        if "error" in metadata:
            return jsonify({"success": False, "error": metadata["error"]}), 400
            
        # Get transcript with improved error handling
        transcript_result = get_transcript(video_id, use_proxy)
            
        # Format response according to MindPal API structure
        result = {
            "success": True,
            "data": {
                "metadata": metadata,
                "transcript": transcript_result["transcript_text"],
                "source": youtube_url,
                "transcript_available": transcript_result["success"]
            }
        }
        
        # Add transcript details if available
        if transcript_result["success"] and "transcript_details" in transcript_result:
            result["data"]["transcript_details"] = transcript_result["transcript_details"]
            result["data"]["transcript_type"] = transcript_result["transcript_type"]
        elif not transcript_result["success"]:
            result["data"]["transcript_error"] = transcript_result["error"]
            
        # Add alternative options if available
        if "alternative_options" in transcript_result:
            result["data"]["alternative_options"] = transcript_result["alternative_options"]
        
        return jsonify(result)
        
    except Exception as e:
        app.logger.error(f"Error in MindPal API: {e}")
        app.logger.error(traceback.format_exc())
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/debug", methods=["POST"])
def debug_request():
    """Debug endpoint to echo back request details"""
    try:
        # Get all headers
        headers = {k: v for k, v in request.headers.items()}

        # Get body
        try:
            if request.is_json:
                body = request.get_json()
            else:
                body = request.data.decode('utf-8')
        except:
            body = "Could not parse body"

        # Get query parameters
        args = {k: v for k, v in request.args.items()}

        response = {
            "received_headers": headers,
            "received_body": body,
            "received_args": args,
            "method": request.method,
            "url": request.url,
            "remote_addr": request.remote_addr,
            "content_type": request.content_type
        }

        return jsonify(response)
    except Exception as e:
        return jsonify({"error": str(e)})

# Default route for testing
@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "message": "YouTube API is running",
        "endpoints": [
            {
                "path": "/api/extract",
                "method": "POST",
                "description": "Extract YouTube video metadata and transcript"
            },
            {
                "path": "/api/mindpal/extract",
                "method": "POST",
                "description": "MindPal-compatible API for YouTube extraction"
            }
        ]
    })

# For local development
if __name__ == "__main__":
    app.run(debug=True)
