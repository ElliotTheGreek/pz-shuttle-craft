import os
import urllib.request

url = "https://drive.google.com/drive/folders/1NpfT3wqe2k3Jwue2xryi7tzxP4bWzETu?usp=sharing"
os.makedirs(".asset-import", exist_ok=True)
with urllib.request.urlopen(url) as response:
    content = response.read()
with open(".asset-import/drive.html", "wb") as output:
    output.write(content)
print("Downloaded folder page:", len(content), "bytes")

text = content.decode("utf-8", "replace")
import re

# Drive embeds child records in callback data. Print compact snippets around
# MIME types and plausible file/folder IDs so the official downloads can be
# retrieved without scraping a third-party mirror.
for match in re.finditer(r"application/(?:vnd\.google-apps\.[a-z-]+|[a-z0-9.+-]+)", text):
    snippet = text[max(0, match.start() - 500):match.end() + 200]
    print("RECORD", snippet.replace("\\u003d", "=").replace("\\x22", '"'))
