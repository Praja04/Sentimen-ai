import urllib.request
import re

# Try different URL formats
channels = [
    ('Bloomberg', 'https://www.youtube.com/@business/live'),
    ('Bloomberg2', 'https://www.youtube.com/@bloombergtv/live'),
    ('NHK', 'https://www.youtube.com/@nhkworldnews/live'),
    ('NHK2', 'https://www.youtube.com/@nhkworldjapan/live'),
    ('DW', 'https://www.youtube.com/@dwnews/live'),
    ('DW2', 'https://www.youtube.com/@dwenglish/live'),
    ('AJ', 'https://www.youtube.com/@aljazeera/live'),
    ('AJ2', 'https://www.youtube.com/@aljazeeraenglish/live'),
    ('France24', 'https://www.youtube.com/@france24english/live'),
    ('CGTN', 'https://www.youtube.com/@cgtnnews/live'),
    ('Wion', 'https://www.youtube.com/@wion/live'),
]

for name, url in channels:
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0'})
        html = urllib.request.urlopen(req, timeout=10).read().decode('utf-8', errors='ignore')
        match = re.search(r'"videoId":"([A-Za-z0-9_-]{11})"', html)
        if match:
            print(f'{name}: {match.group(1)} | url={url}')
        else:
            print(f'{name}: NOT FOUND')
    except Exception as e:
        print(f'{name}: ERROR - {e}')
