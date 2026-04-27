import httpx
import re
import json

async def check_youtube_live(handle_or_channel_id):
    if handle_or_channel_id.startswith('@'):
        url = f"https://www.youtube.com/{handle_or_channel_id}/live"
    else:
        url = f"https://www.youtube.com/channel/{handle_or_channel_id}/live"
    
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.get(url, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
            html = resp.text
            
            # Check if canonical is a watch url
            match = re.search(r'<link rel="canonical" href="https://www.youtube.com/watch\?v=([^"]+)">', html)
            if not match:
                return None
            
            vid_id = match.group(1)
            
            # Verify if it's actually live
            # ytInitialPlayerResponse contains playabilityStatus -> liveStreamability
            if '"isLive":true' in html or '"isLiveBroadcast":true' in html or 'isLiveNow":true' in html:
                return vid_id
            return None
    except Exception as e:
        print(f"Error checking {handle_or_channel_id}: {e}")
        return None

if __name__ == "__main__":
    import asyncio
    async def main():
        print("Bloomberg:", await check_youtube_live("@BloombergTelevision"))
        print("SpaceX:", await check_youtube_live("@SpaceX"))
    asyncio.run(main())
