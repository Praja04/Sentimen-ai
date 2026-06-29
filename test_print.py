import json

db = json.load(open('xedy_v30_data.json', encoding='utf-8'))
for a in db['assets']:
    if a['symbol'] == 'XAUUSD':
        print(a['f4'])
