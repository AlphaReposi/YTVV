import os
import re
import json
import yt_dlp
import requests
import urllib.parse
from   pytube import Search
from   datetime import datetime
from   dotenv import load_dotenv
from   flask import Flask, request, jsonify
from   sentence_transformers import SentenceTransformer, util

# Load environment variables from .env file
load_dotenv()
# Get the API key
API_KEY = os.getenv("API_KEY")
app = Flask(__name__)

model = SentenceTransformer('all-MiniLM-L6-v2')

# Function to generate similar titles
def generate_similar_titles(title):
    base_url = "https://rephrasesrv.gingersoftware.com/Rephrase/secured/rephrase"
    params = {
        "apiKey": "GingerWebsite",
        "clientVersion": "2.0",
        "lang": "en",
        "s": title,
        "size": "8"
    }
    query_string = urllib.parse.urlencode(params, safe="?:")
    url = f"{base_url}?{query_string}"
    response = requests.get(url).json().get('Sentences', [])
    return [f"{i+1}. {sent['Sentence']}" for i, sent in enumerate(response)]

def get_top_search_results(title):
    final_results = []
    results = Search(title).results
    for result in results:
        final_results.append(result.watch_url)
    return final_results

def filter_youtube_results(search_results):
    return [i for i in search_results if i['source'] == 'YouTube']

def reverse_thumbnail_search(thumbnail_url):
    url = "https://google.serper.dev/lens"
    payload = json.dumps({"url": thumbnail_url})
    headers = {
        'X-API-KEY': API_KEY,
        'Content-Type': 'application/json'
    }
    response = requests.request("POST", url, headers=headers, data=payload)
    results = response.json().get('organic', [])

    # Fetch metadata for each YouTube video found in the results
    for result in results:
        if result.get('source') == 'YouTube':
            video_url = result.get('link')
            metadata = get_video_metadata(video_url)  # Fetch metadata using yt_dlp
            if metadata:
                result.update({
                    'views': metadata.get('views', 0),
                    'likes': metadata.get('likes', 0),
                    'comments': metadata.get('comments', 0)
                })
    
    return results
# Function to extract metadata including engagement metrics
def extract_video_id(video_url_or_id):
    """
    Extracts the YouTube video ID from a URL or returns the ID directly if provided.

    :param video_url_or_id: The YouTube video URL or ID.
    :return: The extracted video ID or None if the input is invalid.
    """
    # Regex pattern to match YouTube video IDs in various URL formats
    youtube_regex = (
        r'(?:https?://)?'  # Optional scheme (http or https)
        r'(?:www\.)?'      # Optional "www."
        r'(?:youtube\.com|youtu\.be)'  # Domain name
        r'(?:/watch\?v=|/embed/|/v/|/shorts/|/live/|/)([a-zA-Z0-9_-]{11})'  # Video ID
    )
    
    # Match the regex pattern
    match = re.search(youtube_regex, video_url_or_id)
    if match:
        return match.group(1)  # Return the captured video ID
    else:
        # If no match, assume the input is already a video ID
        if len(video_url_or_id) == 11 and re.match(r'^[a-zA-Z0-9_-]+$', video_url_or_id):
            return video_url_or_id
        return None


def get_youtube_metadata(video):
    video_id = extract_video_id(video)
    """
    Fetches metadata for a YouTube video using the ytapi.apps.mattw.io API.

    :param video_id: The ID of the YouTube video.
    :return: A dictionary containing the simplified metadata of the video.
    """
    # API endpoint
    api_url = "https://ytapi.apps.mattw.io/v3/videos"
    
    # Query parameters
    params = {
        "key": "foo1",  # Static key as per the request data
        "quotaUser": "WHQssHmB6JixluhJzlJjmNzmgBFelxHiKPUofnrx",  # Example quotaUser value
        "part": "snippet,statistics,contentDetails,status",  # Simplified parts for testing
        "id": video_id,  # YouTube video ID
    }
    
    try:
        # Send a GET request to the API with the query parameters
        headers = {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Origin": "https://mattw.io",
            "Referer": "https://mattw.io/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36 Edg/134.0.0.0"
        }
        
        response = requests.get(api_url, params=params, headers=headers)
        
        # Raise an exception if the request was unsuccessful
        response.raise_for_status()
        
        # Parse the JSON response
        metadata = response.json()
        
        # Check if the response contains valid data
        if metadata.get("items"):
            video_data = metadata["items"][0]
            snippet = video_data["snippet"]
            statistics = video_data["statistics"]
            
            # Extract relevant fields
            title = snippet.get("title", "N/A")
            description = snippet.get("description", "N/A")
            video_url = f"https://www.youtube.com/watch?v={video_id}"
            thumbnail_url = snippet["thumbnails"].get("maxres", {}).get("url", "N/A")
            views = statistics.get("viewCount", "N/A")
            likes = statistics.get("likeCount", "N/A")
            comments = statistics.get("commentCount", "N/A")
            upload_date = snippet.get("publishedAt", "N/A").split("T")[0]  # Extract date only
            author = snippet.get("channelTitle", "N/A")
            
            # Return simplified metadata dictionary
            return {
                'title': title,
                'description': description,
                'url': video_url,
                'thumbnail_url': thumbnail_url,
                'views': views,
                'likes': likes,
                'comments': comments,
                'upload_date': upload_date,
                'author': author
            }
        else:
            print("No metadata found for the provided video ID.")
            print(f"Response: {metadata}")
            return None
    
    except requests.exceptions.RequestException as e:
        print(f"An error occurred while fetching metadata: {e}")
        return None
    
# Function to compute cosine similarity using Sentence-BERT
def compute_similarity(text1, text2):
    embedding1 = model.encode(text1, convert_to_tensor=True)
    embedding2 = model.encode(text2, convert_to_tensor=True)
    similarity_score = util.cos_sim(embedding1, embedding2).item()
    return float(round(similarity_score*100, 2))

@app.route('/get-top-search-results/', methods=['POST'])
def api_get_top_search_results():
    data = request.get_json()
    title = data['title']
    results = get_top_search_results(title)
    return jsonify(
        {'results': results}
    )

@app.route('/get-video-metadata/', methods=['POST'])
def api_get_video_metadata():
    data = request.get_json()
    video_url = data.get('video_url')
    data = get_video_metadata(video_url)
    return jsonify(data)

@app.route('/generate-similar-titles/', methods=['POST'])
def api_generate_similar_titles():
    data = request.get_json()
    title = data.get('title')
    data = generate_similar_titles(title)
    return jsonify(
        {'generated_titles': data}
    )

@app.route('/reverse-thumbnail-search/', methods=['POST'])
def api_reverse_thumnail_search():
    data = request.get_json()
    thumbnail_url = data['thumbnail_url']
    results = reverse_thumbnail_search(thumbnail_url)
    return jsonify(results)

@app.route('/filter-youtube-results/', methods=['POST'])
def api_filter_youtube_results():
    data = request.get_json()
    results = list(data)
    youtube_results = filter_youtube_results(results)
    return jsonify(
        {'youtube_results': youtube_results}
    )

@app.route('/compute-similarity/', methods=['POST'])
def api_compute_similarity():
    data = request.get_json()
    video1 = data['video1']
    video2 = data['video2']
    text1 = f"{video1['title']} {video1['description']}"
    text2 = f"{video2['title']} {video2['description']}"
    similarity_score = compute_similarity(text1, text2)
    return jsonify(
        {'similarity': similarity_score}
    )
 
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))  # Render provides PORT dynamically
    app.run(host="0.0.0.0", port=port, debug=True)
