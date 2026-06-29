import urllib.request
import re
try:
    html = urllib.request.urlopen(urllib.request.Request('https://www.youtube.com/@CNBC_ID', headers={'User-Agent': 'Mozilla/5.0'})).read().decode('utf-8')
    match = re.search(r'"channelId":"(UC[a-zA-Z0-9_-]+)"', html)
    if match:
        print("FOUND:", match.group(1))
    else:
        print("NOT FOUND")
except Exception as e:
    print("ERROR:", e)
