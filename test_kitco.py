import urllib.request
from bs4 import BeautifulSoup

try:
    req = urllib.request.Request("https://www.kitco.com/news/", headers={'User-Agent': 'Mozilla/5.0'})
    html = urllib.request.urlopen(req, timeout=10).read()
    soup = BeautifulSoup(html, 'html.parser')
    
    # Let's find some headlines
    # Kitco headlines are usually in specific class names or elements. Let's look for standard links.
    links = []
    for a in soup.find_all('a', href=True):
        if '/news/article/' in a['href'] or '/news/202' in a['href']:
            text = a.get_text(strip=True)
            if len(text) > 20:
                links.append(text)
    
    print("Found links:")
    for l in links[:5]:
        print("-", l)
except Exception as e:
    print("Scrape failed:", e)
