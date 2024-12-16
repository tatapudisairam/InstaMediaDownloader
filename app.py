from flask import Flask, render_template, request, send_file, Response, stream_with_context, jsonify
import requests
import re
import os
import subprocess
import zipfile
from io import BytesIO
import ffmpeg
from datetime import datetime


app = Flask(__name__, static_folder="static")

GOOGLE_SHEET_URL = "https://script.google.com/macros/s/AKfycby-rSPKxhf1JbniV8KxTbF-OXok8UY1_CpTWMew7WHYeHwZ-Hq65u3t9U362TmazEBjPg/exec"
RAPID_API_KEY = '94c11f016cmshcab1e74ebfd86f6p18ec0djsn480d5344d954'

def send_to_google_sheet(url, timestamp):
    data = {
        'url': url,
        'timestamp': timestamp
    }
    print(f"Sending to Google Sheets: {data}")  
    try:
        response = requests.post(GOOGLE_SHEET_URL, data=data)
        response.raise_for_status()
        print("Data sent to Google Sheets successfully.")
    except requests.RequestException as e:
        print(f"Failed to send data to Google Sheets: {e}")

def stream_images(post_code):
    api_url = "https://instagram-scraper-api2.p.rapidapi.com/v1/post_info"
    querystring = {"code_or_id_or_url": post_code}
    headers = {
        "x-rapidapi-key": RAPID_API_KEY,
        "x-rapidapi-host": "instagram-scraper-api2.p.rapidapi.com"
    }

    try:
        response = requests.get(api_url, headers=headers, params=querystring)
        response.raise_for_status()
        data = response.json()

        urls = []

        if 'data' in data:
            if 'carousel_media' in data['data']:
                carousel_media = data['data']['carousel_media']
                for media_item in carousel_media:
                    image_versions = media_item.get('image_versions', {})
                    items = image_versions.get('items', [])
                    if items:
                        first_item_url = items[0].get('url')
                        urls.append(first_item_url)
            else:
                image_versions = data['data'].get('image_versions', {})
                items = image_versions.get('items', [])
                if items:
                    direct_url = items[0].get('url')
                    urls.append(direct_url)

        return urls

    except requests.RequestException as e:
        print(f"Error downloading images: {e}")
        return []


def extract_audio(video_content):
    audio_path = BytesIO()
    try:
        process = subprocess.Popen(
            ['ffmpeg', '-i', 'pipe:0', '-q:a', '0', '-map', 'a', '-f', 'mp3', 'pipe:1'],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

        audio_data, stderr = process.communicate(input=video_content.getvalue())
        
        if process.returncode != 0:
            raise Exception(f"FFmpeg error: {stderr.decode()}")

        audio_path.write(audio_data)
        audio_path.seek(0)
        return audio_path

    except Exception as e:
        raise Exception(f"Failed to extract audio. Error: {e}")

def extract_shortcode(url):
    pattern = r'instagram.com/(?:p|reel)/([^/?]+)'
    match = re.search(pattern, url)
    return match.group(1) if match else None

def stream_reel(post_code):
    api_url = "https://instagram-scraper-api2.p.rapidapi.com/v1/post_info"
    querystring = {"code_or_id_or_url": post_code, "include_insights": "true"}
    headers = {
        "x-rapidapi-key": RAPID_API_KEY,
        "x-rapidapi-host": "instagram-scraper-api2.p.rapidapi.com"
    }

    try:
        response = requests.get(api_url, headers=headers, params=querystring)
        response.raise_for_status()
        data = response.json()

        if 'data' in data and 'video_versions' in data['data']:
            video_versions = data['data']['video_versions']
            if video_versions:
                video_url = video_versions[0]['url']
                video_response = requests.get(video_url, stream=True)
                video_response.raise_for_status()

                video_content = BytesIO()
                for chunk in video_response.iter_content(chunk_size=8192):
                    video_content.write(chunk)

                video_content.seek(0)
                return video_content

    except requests.RequestException as e:
        print(f"Error downloading reel: {e}")
        return None

def stream_profile_pic(username):
    api_url = "https://instagram-scraper-api2.p.rapidapi.com/v1/info"
    querystring = {"username_or_id_or_url": username}
    headers = {
        "x-rapidapi-key": RAPID_API_KEY,
        "x-rapidapi-host": "instagram-scraper-api2.p.rapidapi.com"
    }

    try:
        response = requests.get(api_url, headers=headers, params=querystring)
        response.raise_for_status()
        data = response.json()

        if 'data' in data and 'hd_profile_pic_url_info' in data['data']:
            profile_pic_url = data['data']['hd_profile_pic_url_info']['url']
            pic_response = requests.get(profile_pic_url, stream=True)
            pic_response.raise_for_status()

            return pic_response.iter_content(chunk_size=8192)

    except requests.RequestException as e:
        print(f"Error downloading profile picture: {e}")
        return None






@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        url = request.form['reel_url']
        selection = request.form['download_type']
        shortcode = extract_shortcode(url)

        if shortcode:
            video_content = stream_reel(shortcode)
            if video_content:
                timestamp = datetime.now().strftime("%Y-%m-%d %I:%M %p")
                send_to_google_sheet(url, timestamp) 
                if selection == 'video':
                    return send_file(
                        video_content,
                        as_attachment=True,
                        download_name=f"{shortcode}.mp4",
                        mimetype="video/mp4"
                    )
                elif selection == 'audio':
                    audio_content = extract_audio(video_content)
                    return send_file(
                        audio_content,
                        as_attachment=True,
                        download_name=f"{shortcode}.mp3",
                        mimetype="audio/mpeg"
                    )
            else:
                return "Failed to download the reel. Please try again."
        else:
            return "Invalid Instagram Reel URL. Please try again."

    return render_template('index.html')




@app.route('/download_image', methods=['GET', 'POST'])
def download_image():
    if request.method == 'POST':
        url = request.form['image_url']
        shortcode = extract_shortcode(url)

        if shortcode:
            image_urls = stream_images(shortcode)
            if image_urls:
                # Create a zip file
                zip_buffer = BytesIO()
                with zipfile.ZipFile(zip_buffer, 'w') as zip_file:
                    for idx, img_url in enumerate(image_urls):
                        img_response = requests.get(img_url)
                        img_response.raise_for_status()
                        img_data = BytesIO(img_response.content)
                        zip_file.writestr(f'image_{idx + 1}.jpg', img_data.getvalue())
                zip_buffer.seek(0)
                timestamp = datetime.now().strftime("%Y-%m-%d %I:%M %p")
                send_to_google_sheet(url, timestamp)
                return send_file(
                    zip_buffer,
                    as_attachment=True,
                    download_name='images.zip',
                    mimetype='application/zip'
                )
            else:
                return "Failed to retrieve the images. Please try again."
        else:
            return "Invalid Instagram Image URL. Please try again."

    return render_template('download_image.html')




@app.route('/download_profile_pic', methods=['GET', 'POST'])
def download_profile_pic():
    if request.method == 'POST':
        username = request.form['username'].strip()  # Strip any leading/trailing whitespace
        username = username.lstrip('@')  # Remove leading '@' if present

        pic_content = stream_profile_pic(username)
        if pic_content:
            timestamp = datetime.now().strftime("%Y-%m-%d %I:%M %p")
            send_to_google_sheet(username, timestamp) 
            return Response(
                stream_with_context(pic_content),
                mimetype="image/jpeg",
                headers={"Content-Disposition": f"attachment;filename={username}_profile_pic.jpg"}
            )
        else:
            return "Failed to download the profile picture. Please try again."

    return render_template('download_profile_pic.html')





@app.route("/contact")
def contact():
    return render_template("contact.html")




if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
