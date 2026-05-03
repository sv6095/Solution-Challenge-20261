import sys, os
sys.path.insert(0, r'd:\Praecantator\Backend')
os.environ.setdefault('NEWSAPI_API_KEY', 'ca5b4242c8f748649ae721a1a5ff022a')
os.environ.setdefault('GNEWS_API_KEY', '8fc968d93d6742693a6714f2440cd869')
os.environ.setdefault('NASA_FIRMS_MAP_KEY', 'd13ea2d01a49c3e04930501af8ba7006')
os.environ.setdefault('MASTODON_INSTANCE', 'mastodon.social')

import asyncio
from agents.signal_agent import fetch_gdelt, fetch_nasa_eonet, fetch_newsapi, fetch_gnews
from agents.extended_signal_agent import (
    fetch_gdacs, fetch_usgs_earthquakes, fetch_reliefweb,
    fetch_hackernews_sentiment, fetch_mastodon_sentiment, fetch_ofac_sanctions
)

async def test():
    print("EONET:", len(await fetch_nasa_eonet()))
    print("GDELT:", len(await fetch_gdelt()))
    print("GDACS:", len(await fetch_gdacs()))
    print("USGS:", len(await fetch_usgs_earthquakes()))
    print("ReliefWeb:", len(await fetch_reliefweb()))
    print("OFAC:", len(await fetch_ofac_sanctions()))
    print("HackerNews:", len(await fetch_hackernews_sentiment()))
    print("Mastodon:", len(await fetch_mastodon_sentiment()))
    print("NewsAPI:", len(await fetch_newsapi('ca5b4242c8f748649ae721a1a5ff022a')))
    print("GNews:", len(await fetch_gnews('8fc968d93d6742693a6714f2440cd869')))

asyncio.run(test())
