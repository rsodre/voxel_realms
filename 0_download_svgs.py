import json
import requests
import asyncio
import glob

NUM_SVGS = 8000

paths = glob.glob("svgs/*.svg")
done = [int(path.replace("svgs/","").replace("svgs\\","").replace(".svg","")) for path in paths]
print(done)

with open("resources/database.json", encoding="utf8") as file:
    data = json.load(file)

async def download(i):
    url = data[str(i)]["image"]
    # url = url.replace("https://gateway.pinata.cloud/ipfs/", "https://ipfs.io/ipfs/")
    url = url.replace("https://gateway.pinata.cloud/ipfs/", "http://ipfs.localhost:8084/ipfs/")
    # print(url)
    r = requests.get(url, allow_redirects=True)
    with open(f"svgs/{i}.svg", "wb") as f:
        f.write(r.content)
    print(i)

async def main():
    for i in range(NUM_SVGS):
        if i+1 not in done:
            await download(i+1)

asyncio.run(main())
