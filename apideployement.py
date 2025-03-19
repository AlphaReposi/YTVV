import os
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
def get_video_metadata(video_url):
    try:
        # Fetch metadata using yt_dlp
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "logtostderr": False
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(video_url, download=False)
            title = info_dict.get("title", "Title not found")
            description = info_dict.get("description", "Description not found")
            thumbnail_url = info_dict.get("thumbnail", "Thumbnail not found")
            views = info_dict.get("view_count", 0)
            likes = info_dict.get("like_count", 0)
            comments = info_dict.get("comment_count", 0)
            upload_date = datetime.strptime(info_dict.get("upload_date", "19700101"), "%Y%m%d").date()
            author = info_dict.get('channel', 'Unknown')

        return {
            'title': title,
            'description': description,
            'url': video_url,
            'thumbnail_url': thumbnail_url,
            'views': views,
            'likes': likes,
            'comments': comments,
            'upload_date': upload_date,
            'author': author  # Add author to metadata
        }

    except Exception as e:
        print(f"Error fetching metadata: {e}")
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
    app.run(debug=True)