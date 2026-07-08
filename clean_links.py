import os, re, glob

def clean_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Remove single line or multi-line links to /backtest and /Monitor
    content = re.sub(r'<a[^>]*href=[\'"]/(backtest|Monitor|monitor)[\'"][^>]*>.*?</a>', '', content, flags=re.IGNORECASE | re.DOTALL)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
        
    print(f'Cleaned {filepath}')

files = glob.glob(r'C:\Antigravity\static\*.html') + glob.glob(r'C:\Antigravity\templates\*.html')
for file in files:
    clean_file(file)
