import urllib.request
import re

def get_live_video_id(handle):
    url = f"https://www.youtube.com/{handle}/live"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            html = response.read().decode('utf-8')
            # Look for canonical link
            match = re.search(r'<link rel="canonical" href="https://www.youtube.com/watch\?v=([^"]+)">', html)
            if match:
                vid_id = match.group(1)
                # Ensure it's actually a live stream by checking for "isLiveBroadcast":true or similar
                if '"isLiveBroadcast":true' in html or '"isLiveNow":true' in html or 'LiveStream' in html or 'isLive' in html:
                    return vid_id
                else:
                    return f"NOT_LIVE ({vid_id})"
            return "NO_CANONICAL"
    except Exception as e:
        return str(e)

print("Bloomberg:", get_live_video_id("@BloombergTelevision"))
print("SpaceX:", get_live_video_id("@SpaceX"))
