import os
import re
import json
import yt_dlp
import requests
import urllib.parse
from   pytube import Search
from   datetime import datetime
from   bs4 import BeautifulSoup
from   dotenv import load_dotenv
from   flask import Flask, request, jsonify

# Load environment variables from .env file
load_dotenv()
# Get the API key
API_KEY = os.getenv("API_KEY")
app = Flask(__name__)

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
    video_id = video_url.split("v=")[-1]  # Extract video ID
    SCRAPE_DO_API_KEY = "06323a5daf6443fd8d6adeda0fa328b8352cf3ccd1a"
    # Scrape.do API URL
    scrape_do_url = f"http://api.scrape.do?token={SCRAPE_DO_API_KEY}&url={video_url}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.youtube.com/"
    }

    # Fetch main video page via Scrape.do
    response = requests.get(scrape_do_url, headers=headers)
    print("Response:" , response)

    # Parse the page to extract initial JSON
    soup = BeautifulSoup(response.text, "html.parser")
    scripts = soup.find_all("script")

    video_details = None
    for script in scripts:
        if "var ytInitialPlayerResponse" in script.text:
            json_text = re.search(r"var ytInitialPlayerResponse\s*=\s*(\{.*?\});", script.text)
            if json_text:
                video_details = json.loads(json_text.group(1))["videoDetails"]
                break

    if not video_details:
        raise Exception("Failed to extract video metadata")

    # Extract basic details
    title = video_details.get("title", "Title not found")
    author = video_details.get("author", "Unknown")
    thumbnail_url = video_details["thumbnail"]["thumbnails"][-1]["url"]
    views = int(video_details.get("viewCount", 0))
    upload_date = video_details.get("publishDate", "1970-01-01")
    upload_date = datetime.strptime(upload_date, "%Y-%m-%d").date()

    # Extract description
    description = video_details.get("shortDescription", "No description available")

    # Fetch likes count using YouTube's AJAX request via Scrape.do
    likes_url = f"https://returnyoutubedislikeapi.com/votes?videoId={video_id}"
    likes_response = requests.get(likes_url, headers=headers)
    likes = 0
    if likes_response.status_code == 200:
        likes_data = likes_response.json()
        likes = likes_data.get("likes", 0)

    # ✅ Correct YouTube API Request to Get Comments Count via Scrape.do
    api_url = f"http://api.scrape.do?token={SCRAPE_DO_API_KEY}&url=https://www.youtube.com/youtubei/v1/next"
    payload = {
        "context": {
            "client": {
                "clientName": "WEB",
                "clientVersion": "2.20240214"
            }
        },
        "videoId": video_id
    }
    comments = 0
    comments_response = requests.post(api_url, headers=headers, json=payload)
    if comments_response.status_code == 200:
        comments_data = comments_response.json()
        try:
            comment_section = comments_data["contents"]["twoColumnWatchNextResults"]\
                ["results"]["results"]["contents"]
            for item in comment_section:
                if "itemSectionRenderer" in item:
                    comments_label = item["itemSectionRenderer"]["contents"][0]\
                        ["commentsEntryPointHeaderRenderer"]["commentCount"]["simpleText"]
                    comments = int(comments_label.replace(",", ""))
                    break  # Stop when we find it
        except (KeyError, IndexError, ValueError):
            comments = 0

    return {
        "title": title,
        "description": description,
        "author": author,
        "url": video_url,
        "thumbnail_url": thumbnail_url,
        "views": views,
        "likes": likes,
        "comments": comments,
        "upload_date": upload_date
    }


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
    body = {'text_1': text1, 'text_2': text2}
    api_url = 'https://api.api-ninjas.com/v1/textsimilarity'
    response = requests.post(api_url, headers={'X-Api-Key': 'iA1uG7UEmJtOuvU1MrS9Kw==bLdVLc81sdAwwpRd'}, json=data)
    similarity_score = response.json()['similarity']
    return jsonify(
        {'similarity': round(similarity_score*100, 2)}
    )
 
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))  # Render provides PORT dynamically
    app.run(host="0.0.0.0", port=port, debug=True)
