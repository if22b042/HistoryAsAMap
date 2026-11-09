"""Does the Wikipedia intro of each event link to the person's article?  Small sample, read-only."""
import json, re, sqlite3, sys, time, urllib.error, urllib.parse, urllib.request
sys.stdout.reconfigure(encoding="utf-8")
PERSON = {"washington": "George_Washington", "wellington": "Arthur_Wellesley,_1st_Duke_of_Wellington", "hannibal": "Hannibal"}
term = sys.argv[1]; limit = int(sys.argv[2]) if len(sys.argv) > 2 else 25
con = sqlite3.connect("file:../old/instance/haam.db?mode=ro", uri=True)
rows = con.execute("select title, wiki_url, summary from haam_events where status='approved' and (summary like ? or title like ?)",
                   (f"%{term}%", f"%{term}%")).fetchall()
rows = [r for r in rows if re.search(rf"\b{term}\b", r[0] + " " + (r[2] or ""), re.I)][:limit]
def intro_links(title):
    q = urllib.parse.urlencode({"action": "parse", "page": title, "prop": "text", "section": 0, "format": "json", "redirects": 1})
    req = urllib.request.Request("https://en.wikipedia.org/w/api.php?" + q, headers={"User-Agent": "haam-analysis/0.1 (local research script)"})
    for wait in (0, 5, 15, 30):
        time.sleep(wait + 1.2)  # be polite: ~1 request per second, back off on 429
        try:
            html = json.load(urllib.request.urlopen(req, timeout=20))["parse"]["text"]["*"]
            break
        except urllib.error.HTTPError as e:
            if e.code != 429: raise
    else:
        raise RuntimeError("rate limited")
    return set(urllib.parse.unquote(m) for m in re.findall(r'href="/wiki/([^"#]+)"', html))
for title, url, summary in rows:
    page = urllib.parse.unquote(url.rsplit("/wiki/", 1)[-1])
    try:
        links = intro_links(page)
        hit = PERSON[term] in links
        print(f"{'LINKED ' if hit else 'no link'} | {title} | person links in intro: {[l for l in links if term in l.lower()][:4]}")
    except Exception as e:
        print("error", title, e)
