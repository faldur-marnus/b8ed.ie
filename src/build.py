#!/usr/bin/env python3
"""Build b8ed.ie from src/posts/*.md into static HTML at the repo root.

Usage:  python3 src/build.py

Post format: front matter between --- lines, then a light Markdown body.
  title, dek, date (YYYY-MM-DD HH:MM), section, segment, thumb, tone, bait (1-5), author
  section: sport | pop-culture | politics | comedy
  segment: fake-news | rage-bait | vox-pop | live | comedy-night | (blank)
  tone:    red | deep | ink | pink | stone
Body: blank-line separated blocks. Supports ## / ### headings, > quotes
(a following "-- Name" line becomes the citation), - and 1. lists, ::: callouts,
**bold**, *italic*, [links](url). In live posts, "@@ 20:41" starts a timeline entry.
"""
import datetime as dt
import html
import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
POSTS = ROOT / "src" / "posts"
SITE = "https://b8ed.ie"
CONTACT = "hello@b8ed.ie"

SECTIONS = {
    "sport": ("Sport", "Vox pops, live updates and reaction across rugby, football, GAA and the League of Ireland.", "Every Wednesday and Saturday"),
    "pop-culture": ("Pop Culture", "Telly, gigs, the group chat and everything the country is giving out about this week.", "Every Monday, Tuesday and Thursday"),
    "politics": ("Politics", "The Dáil, the budget and the lamppost posters that outlived the campaign.", "Every Sunday"),
    "comedy": ("Comedy", "Material from the B8ED Comedy Night and the comedians coming up through it.", "Every Friday"),
}
SEGMENTS = {
    "fake-news": ("Baited Fake News", "Satirical headlines and stories that parody the clickbait news cycle. None of it happened. Most of it could have.", "SATIRE"),
    "rage-bait": ("Rage Bait", "Deliberately provocative takes that poke fun at outrage culture. Fuming? Good. That's the point.", "RAGE BAIT"),
    "vox-pop": ("Vox Pops", "Comedians ask fans the questions nobody needed answered, before and after the game.", "VOX POP"),
    "live": ("Live", "Real-time coverage that keeps you on the page.", "LIVE"),
    "comedy-night": ("Comedy Night", "Our monthly live night in Dublin.", "COMEDY NIGHT"),
}
NAV = [("Fake News", "/fake-news/"), ("Rage Bait", "/rage-bait/"), ("Sport", "/sport/"),
       ("Pop Culture", "/pop-culture/"), ("Politics", "/politics/"), ("Comedy", "/comedy/"),
       ("Vox Pops", "/vox-pops/")]
SEGMENT_PATHS = {"fake-news": "fake-news", "rage-bait": "rage-bait", "vox-pop": "vox-pops"}
WEEK = [("Mon", "Pop culture", ""), ("Tue", "Pop culture", ""), ("Wed", "Sport", "sport"),
        ("Thu", "Pop culture", ""), ("Fri", "Comedy", "comedy"), ("Sat", "Sport", "sport"),
        ("Sun", "Politics", "politics")]
GENERATED = ["a", "sport", "pop-culture", "politics", "comedy", "fake-news", "rage-bait",
             "vox-pops", "advertise", "about", "index.html", "404.html", "sitemap.xml", "feed.xml"]

e = html.escape


# ---------------------------------------------------------------- parsing
def inline(s):
    s = e(s, quote=False)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?!\w)", r"<em>\1</em>", s)
    s = re.sub(r"\[(.+?)\]\((.+?)\)", lambda m: f'<a href="{m.group(2)}">{m.group(1)}</a>', s)
    return s


def render_blocks(text):
    out = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = block.strip().splitlines()
        first = lines[0]
        if first.startswith("## "):
            out.append(f"<h2>{inline(first[3:])}</h2>")
        elif first.startswith("### "):
            out.append(f"<h3>{inline(first[4:])}</h3>")
        elif first.startswith(">"):
            quote = [l.lstrip("> ").rstrip() for l in lines if l.startswith(">")]
            cite = [l[2:].strip() for l in lines if l.startswith("--")]
            c = f"<cite>{inline(cite[0])}</cite>" if cite else ""
            out.append(f"<blockquote><p>{inline(' '.join(quote))}</p>{c}</blockquote>")
        elif first.startswith("- "):
            out.append("<ul>" + "".join(f"<li>{inline(l[2:])}</li>" for l in lines) + "</ul>")
        elif re.match(r"\d+\. ", first):
            out.append("<ol>" + "".join(f"<li>{inline(re.sub(r'^\d+\. ', '', l))}</li>" for l in lines) + "</ol>")
        elif first.startswith(":::"):
            out.append(f'<p class="callout">{inline(" ".join(lines[1:] if first.strip() == ":::" else [first[3:]] + lines[1:]))}</p>')
        else:
            out.append(f"<p>{inline(' '.join(lines))}</p>")
    return "\n".join(out)


def render_body(post):
    body = post["body"]
    if post["segment"] != "live" or "@@" not in body:
        return f'<div class="prose">{render_blocks(body)}</div>'
    intro, *entries = re.split(r"^@@ ", body, flags=re.M)
    items = []
    for chunk in reversed(entries):  # newest first
        t, _, rest = chunk.partition("\n")
        items.append(f'<li class="entry"><time>{e(t.strip())}</time>{render_blocks(rest)}</li>')
    return (f'<div class="prose">{render_blocks(intro) if intro.strip() else ""}'
            f'<div class="live-head"><span class="live-pill"><span class="dot"></span>LIVE</span>'
            f'<span class="meta">Newest first · {len(entries)} updates</span></div>'
            f'<ol class="timeline">{"".join(items)}</ol></div>')


def load_posts():
    posts = []
    for path in sorted(POSTS.glob("*.md")):
        raw = path.read_text(encoding="utf-8")
        _, fm, body = raw.split("---", 2)
        meta = {}
        for line in fm.strip().splitlines():
            k, _, v = line.partition(":")
            meta[k.strip()] = v.strip()
        slug = re.sub(r"^\d{4}-\d{2}-\d{2}-", "", path.stem)
        posts.append({
            "slug": slug,
            "url": f"/a/{slug}/",
            "title": meta["title"],
            "dek": meta.get("dek", ""),
            "date": dt.datetime.strptime(meta["date"], "%Y-%m-%d %H:%M"),
            "section": meta["section"],
            "segment": meta.get("segment", ""),
            "thumb": meta.get("thumb", "B8"),
            "tone": meta.get("tone", "red"),
            "bait": int(meta.get("bait", 3)),
            "author": meta.get("author", "B8ED Staff"),
            "featured": meta.get("featured", "") == "yes",
            "rank": int(meta.get("rank", 99)),
            "body": body,
        })
    posts.sort(key=lambda p: p["date"], reverse=True)
    return posts


# ---------------------------------------------------------------- partials
def fmt_date(d):
    return d.strftime("%a %-d %b %Y")


def fmt_time(d):
    return d.strftime("%a %-d %b, %H:%M")


def kicker(p):
    sec = SECTIONS[p["section"]][0]
    seg = SEGMENTS.get(p["segment"], ("",))[0]
    seg_html = f'<span class="seg">{e(seg)}</span>' if seg and seg != sec else ""
    return f'<div class="kicker">{e(sec)}{seg_html}</div>'


def thumb_size(text):
    """Largest font size (in cqw) at which the thumb text wraps into the tile."""
    words = text.split()
    for fs in range(34, 7, -1):
        char_w, lines, cur = 0.68 * fs, 1, 0.0
        if max(len(w) for w in words) * char_w > 84:
            continue
        for w in words:
            need = len(w) * char_w + (char_w * 0.4 if cur else 0)
            if cur and cur + need > 84:
                lines, cur = lines + 1, len(w) * char_w
            else:
                cur += need
        if lines * 0.92 * fs <= 44:
            return fs
    return 8


def thumb(p, extra=""):
    t = p["thumb"]
    fs = thumb_size(t)
    badge = ""
    if p["segment"] == "live":
        badge = '<span class="badge"><span class="live-dot"></span>Live</span>'
    elif p["segment"] in SEGMENTS:
        badge = f'<span class="badge">{SEGMENTS[p["segment"]][2]}</span>'
    play = '<span class="play" aria-hidden="true"></span>' if p["segment"] == "vox-pop" else ""
    return (f'<div class="thumb t-{p["tone"]} {extra}" style="--fs:{fs}cqw" aria-hidden="true">'
            f'{badge}<span class="big">{e(t)}</span>{play}</div>')


def card(p, dek=True):
    d = f'<p class="dek">{e(p["dek"])}</p>' if dek and p["dek"] else ""
    return (f'<a class="card" href="{p["url"]}">{thumb(p)}<div class="txt">{kicker(p)}'
            f'<h3>{e(p["title"])}</h3>{d}<span class="meta">{fmt_date(p["date"])}</span></div></a>')


def row(p):
    return (f'<a class="card row" href="{p["url"]}">{thumb(p)}<div class="txt">{kicker(p)}'
            f'<h3>{e(p["title"])}</h3></div></a>')


def most_baited(posts):
    ranked = sorted(posts, key=lambda p: (p["rank"], -p["bait"], -p["date"].timestamp()))[:5]
    items = "".join(f'<li><a href="{p["url"]}">{e(p["title"])}</a></li>' for p in ranked)
    return f'<section class="widget"><h2>Most <span>Baited</span></h2><ol class="most">{items}</ol></section>'


def mini_week():
    items = "".join(f'<li data-day="{(i + 1) % 7}"><b class="{cls}">{d}</b>{t}</li>' for i, (d, t, cls) in enumerate(WEEK))
    return (f'<section class="widget"><h2>This week on <span>B8ED</span></h2><ol class="mini-week">{items}</ol>'
            f'<p class="meta" style="margin-top:10px">Every day has an owner. New content, every day of the week.</p></section>')


def ad(tall=False):
    cls = "ad tall" if tall else "ad"
    return (f'<a class="{cls}" href="/advertise/"><small>Advertisement</small>'
            f'<strong>Your brand here. Mid-scroll. Thumb hovering.</strong>'
            f'<span>This space is for sale. Advertise with B8ED &rarr;</span></a>')


def signup():
    return f'''<section class="signup" id="list">
  <div>
    <h2>Get on <em>the B8ED list.</em></h2>
    <p>The best of the week in your inbox, plus first dibs on our competitions for concert and festival tickets. No algorithm can take it off you.</p>
  </div>
  <div>
    <form data-signup>
      <label class="sr-only" for="signup-email">Email address</label>
      <input id="signup-email" type="email" name="email" placeholder="Your email" required autocomplete="email">
      <button class="btn btn-ink" type="submit">Sign me up</button>
    </form>
    <p class="fine">We'll only email you B8ED stuff. Unsubscribe whenever.</p>
  </div>
</section>'''


def share(p):
    url = SITE + p["url"]
    from urllib.parse import quote
    q = quote(f'{p["title"]} {url}')
    return (f'<div class="share"><span>Share the bait:</span>'
            f'<a href="https://wa.me/?text={q}" target="_blank" rel="noopener">WhatsApp</a>'
            f'<a href="https://x.com/intent/post?url={quote(url)}&text={quote(p["title"])}" target="_blank" rel="noopener">X</a>'
            f'<a href="https://www.facebook.com/sharer/sharer.php?u={quote(url)}" target="_blank" rel="noopener">Facebook</a>'
            f'<button type="button" data-copy="{e(url)}">Copy link</button></div>')


def reactions(p):
    return (f'<section class="react" data-react="{p["slug"]}"><h2>How baited are you?</h2><div class="btns">'
            '<button type="button" aria-pressed="false" data-r="fuming">😡 Fuming</button>'
            '<button type="button" aria-pressed="false" data-r="dead">😂 Dead</button>'
            '<button type="button" aria-pressed="false" data-r="eyeroll">🙄 Eye-roll</button>'
            '<button type="button" aria-pressed="false" data-r="sharing">📲 Sending to the group chat</button>'
            '</div><p class="said" aria-live="polite"></p></section>')


def layout(title, body, *, desc, path, active="", og_title=None, og_type="website"):
    full_title = f"{title} | B8ED.ie" if title != "B8ED.ie" else "B8ED.ie"
    nav = "".join(f'<li><a href="{u}"{" aria-current=\"page\"" if u == active else ""}>{n}</a></li>' for n, u in NAV)
    ticker_items = "".join(f'<a href="{p["url"]}">{e(p["title"])}</a>' for p in TICKER)
    ld = json.dumps({"@context": "https://schema.org", "@type": "WebSite", "name": "B8ED.ie", "url": SITE + "/"})
    return f'''<!doctype html>
<html lang="en-IE">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(full_title)}</title>
<meta name="description" content="{e(desc)}">
<link rel="canonical" href="{SITE}{path}">
<link rel="icon" type="image/png" href="/favicon.png">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<link rel="alternate" type="application/rss+xml" title="B8ED.ie" href="/feed.xml">
<link rel="preload" href="/fonts/poppins-latin-800-normal.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="/assets/site.css">
<meta name="theme-color" content="#f80000">
<meta property="og:site_name" content="B8ED.ie">
<meta property="og:title" content="{e(og_title or title)}">
<meta property="og:description" content="{e(desc)}">
<meta property="og:type" content="{og_type}">
<meta property="og:url" content="{SITE}{path}">
<meta property="og:image" content="{SITE}/og.png">
<meta name="twitter:card" content="summary_large_image">
<script type="application/ld+json">{ld}</script>
</head>
<body>
<div class="util"><div class="wrap">
  <span><b data-today-date>{fmt_date(BUILD_DATE)}</b> · <span class="today-theme" data-today-theme></span></span>
  <nav aria-label="Utility"><a href="/about/">About</a><a href="/advertise/">Advertise</a><a href="/about/#write">Write for us</a><a href="/#list">Newsletter</a></nav>
</div></div>
<header class="mast"><div class="wrap">
  <a class="logo" href="/" aria-label="B8ED.ie home"><img src="/logo.png" width="1200" height="541" alt="b8ed.ie"></a>
  <nav aria-label="Sections"><ul>{nav}</ul></nav>
  <a class="sub-btn" href="/#list">Get the list</a>
</div></header>
<div class="ticker" aria-label="Latest headlines"><div class="wrap">
  <span class="tag">Breaking-ish</span>
  <div class="track"><div class="run">{ticker_items}{ticker_items.replace('<a ', '<a tabindex="-1" aria-hidden="true" ')}</div></div>
</div></div>
<main>
{body}
</main>
<footer class="site"><div class="wrap">
  <div class="cols">
    <div>
      <a class="flogo" href="/"><img src="/logo.png" width="1200" height="541" alt="b8ed.ie"></a>
      <p>A satirical Irish media page covering sport, pop culture, politics and comedy. It plays the engagement game and laughs at it.</p>
    </div>
    <div><h2>Sections</h2><ul>{"".join(f'<li><a href="{u}">{n}</a></li>' for n, u in NAV)}</ul></div>
    <div><h2>B8ED</h2><ul><li><a href="/about/">About</a></li><li><a href="/about/#satire">Satire notice</a></li><li><a href="/about/#write">Write for us</a></li><li><a href="/a/comedy-night-open-mic/">Comedy night</a></li></ul></div>
    <div><h2>Work with us</h2><ul><li><a href="/advertise/">Advertise</a></li><li><a href="/advertise/#partner">Partnerships</a></li><li><a href="mailto:{CONTACT}">{CONTACT}</a></li><li><a href="/feed.xml">RSS</a></li></ul></div>
  </div>
  <div class="legal"><span>© {BUILD_DATE.year} B8ED.ie · Dublin, Ireland</span><span>Stories marked SATIRE are made up. If you believed one, that's sort of the point.</span></div>
</div></footer>
<script>
(function () {{
  var themes = {{Mon:"Pop culture day",Tue:"Pop culture day",Wed:"Sport day",Thu:"Pop culture day",Fri:"Comedy day",Sat:"Sport day",Sun:"Politics day"}};
  try {{
    var now = new Date();
    var day = new Intl.DateTimeFormat("en-IE", {{weekday:"short", timeZone:"Europe/Dublin"}}).format(now).slice(0,3);
    var d = document.querySelector("[data-today-date]");
    if (d) d.textContent = new Intl.DateTimeFormat("en-IE", {{weekday:"long", day:"numeric", month:"long", timeZone:"Europe/Dublin"}}).format(now);
    var t = document.querySelector("[data-today-theme]");
    if (t) t.textContent = "Today is " + themes[day];
    var idx = ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"].indexOf(day);
    document.querySelectorAll('.mini-week [data-day="' + idx + '"]').forEach(function (el) {{ el.classList.add("today"); }});
  }} catch (e) {{}}

  document.querySelectorAll("[data-copy]").forEach(function (b) {{
    b.addEventListener("click", function () {{
      try {{ navigator.clipboard.writeText(b.dataset.copy); b.textContent = "Copied. Go on."; }} catch (e) {{}}
    }});
  }});

  var lines = {{fuming:"Fuming. Perfect. Our work here is done.", dead:"Glad someone's laughing.", eyeroll:"Eye-roll noted. You're still reading though.", sharing:"Good. The group chat deserves this."}};
  document.querySelectorAll("[data-react]").forEach(function (box) {{
    var key = "b8ed-react-" + box.dataset.react, saved = null;
    try {{ saved = localStorage.getItem(key); }} catch (e) {{}}
    var said = box.querySelector(".said");
    function set(r) {{
      box.querySelectorAll("button").forEach(function (b) {{ b.setAttribute("aria-pressed", b.dataset.r === r ? "true" : "false"); }});
      said.textContent = r ? lines[r] : "";
    }}
    if (saved) set(saved);
    box.addEventListener("click", function (ev) {{
      var b = ev.target.closest("button"); if (!b) return;
      var r = b.getAttribute("aria-pressed") === "true" ? null : b.dataset.r;
      set(r);
      try {{ r ? localStorage.setItem(key, r) : localStorage.removeItem(key); }} catch (e) {{}}
    }});
  }});

  document.querySelectorAll("[data-signup]").forEach(function (f) {{
    f.addEventListener("submit", function (ev) {{
      ev.preventDefault();
      var email = f.querySelector("input").value;
      location.href = "mailto:{CONTACT}?subject=" + encodeURIComponent("Add me to the B8ED list") + "&body=" + encodeURIComponent("Please add " + email + " to the B8ED list.");
    }});
  }});
}})();
</script>
</body>
</html>
'''


# ---------------------------------------------------------------- pages
def section_band(title, sub, href, posts, cls=""):
    if not posts:
        return ""
    return f'''<section class="band {cls}"><div class="wrap">
  <div class="sec-head"><h2>{e(title)}<small>{e(sub)}</small></h2><a href="{href}">More &rarr;</a></div>
  <div class="grid-4">{"".join(card(p, dek=False) for p in posts[:4])}</div>
</div></section>'''


def home(posts):
    lead = next((p for p in posts if p["featured"]), posts[0])
    rest = [p for p in posts if p is not lead]
    secondary = rest[:4]
    used = {lead["slug"], *(p["slug"] for p in secondary)}
    def pick(f, n=4):
        found = [p for p in posts if f(p) and p["slug"] not in used][:n]
        used.update(p["slug"] for p in found)
        return found
    live = [p for p in posts if p["segment"] == "live"]
    live_strip = ""
    if live and live[0] is not lead:
        lp = live[0]
        live_strip = (f'<div class="wrap"><a class="live-strip" href="{lp["url"]}"><span class="live-pill"><span class="dot"></span>LIVE</span>'
                      f'<div><h3>{e(lp["title"])}</h3><p>{e(lp["dek"])}</p></div><span class="go">Follow live &rarr;</span></a></div>')

    body = f'''
<div class="wrap lead-block">
  <a class="card lead" href="{lead["url"]}">{thumb(lead)}<div class="txt">{kicker(lead)}<h2>{e(lead["title"])}</h2><p class="dek">{e(lead["dek"])}</p><span class="meta">{fmt_time(lead["date"])} · {e(lead["author"])}</span></div></a>
  <div class="stack">{"".join(row(p) for p in secondary)}</div>
  <div class="side">{most_baited(posts)}{mini_week()}</div>
</div>
{live_strip}
<div class="wrap ad-wrap">{ad()}</div>
{section_band("Baited Fake News", "Satire. None of this happened.", "/fake-news/", pick(lambda p: p["segment"] == "fake-news"))}
{section_band("Sport", "Vox pops, live updates and reaction. Wednesdays and Saturdays.", "/sport/", pick(lambda p: p["section"] == "sport"), "dark")}
{section_band("Rage Bait", "Fuming? Good.", "/rage-bait/", pick(lambda p: p["segment"] == "rage-bait"), "alt")}
<section class="band red"><div class="wrap promo">
  <div>
    <div class="kicker" style="color:var(--pink)">Monthly · Dublin</div>
    <h2>The B8ED Comedy Night</h2>
    <p>Big names bring the crowd. New acts get the open mic. The best of them end up on B8ED, on match-day vox pops, and on podcasts.</p>
    <a class="btn btn-white" href="/a/comedy-night-open-mic/">Get an open mic slot</a>
  </div>
  <ul>
    <li><b>Headline names</b>Comedians with big followings, live in a Dublin bar.</li>
    <li><b>Open mic</b>New acts fill the roster. We're watching.</li>
    <li><b>Then Friday</b>The best bits go up on B8ED every Comedy Friday.</li>
  </ul>
</div></section>
{section_band("Pop Culture", "Mondays, Tuesdays, Thursdays.", "/pop-culture/", pick(lambda p: p["section"] == "pop-culture"))}
{section_band("Politics", "Sundays. Sorry.", "/politics/", pick(lambda p: p["section"] == "politics"), "alt")}
<section class="band"><div class="wrap">{signup()}</div></section>
'''
    return layout("B8ED.ie", body, path="/", desc="B8ED.ie: satirical Irish news, sport, pop culture, politics and comedy. It plays the engagement game and laughs at it.")


def listing(title, desc, when, path, items, tone="red"):
    color = {"red": "band red", "ink": "band dark", "deep": "band red"}[tone]
    style = ' style="background:var(--red-deep)"' if tone == "deep" else ""
    when_html = f'<span class="when">{e(when)}</span>' if when else ""
    grid = "".join(card(p) for p in items) or '<p>Nothing here yet. Check back tomorrow, we post every day.</p>'
    body = f'''<section class="{color} sec-hero"{style}><div class="wrap"><h1>{e(title)}</h1><p>{e(desc)}</p>{when_html}</div></section>
<div class="wrap" style="padding-block:36px 56px"><div class="grid-3">{grid}</div>
<div style="margin-top:44px">{ad()}</div></div>'''
    return layout(title, body, path=path, active=path, desc=desc)


def article(p, posts):
    sec_name = SECTIONS[p["section"]][0]
    pills = f'<a href="/{p["section"]}/">{e(sec_name)}</a>'
    if p["segment"] == "fake-news":
        pills += '<span class="pill satire">Satire</span>'
    elif p["segment"] == "rage-bait":
        pills += '<span class="pill">Rage Bait</span>'
    elif p["segment"] == "vox-pop":
        pills += '<span class="pill">Vox Pop</span>'
    elif p["segment"] == "live":
        pills += '<span class="live-pill"><span class="dot"></span>LIVE</span>'
    hooks = "🎣" * p["bait"] + f'<span class="off">{"🎣" * (5 - p["bait"])}</span>'
    if p["segment"] == "vox-pop":
        hero = (f'<figure class="art-hero video">{thumb(p)}<span class="note">Video · full vox pop on our socials</span></figure>')
    else:
        hero = f'<figure class="art-hero">{thumb(p)}</figure>'
    satire_note = ""
    if p["segment"] == "fake-news":
        satire_note = '<p class="callout" style="margin-top:28px;max-width:40rem;font-size:.92rem">This is a <strong>Baited Fake News</strong> story. It is satire. It did not happen, and any resemblance to an actual person is a coincidence. <a href="/about/#satire" style="color:var(--red)">More on that</a>.</p>'
    related = [q for q in posts if q is not p and q["section"] == p["section"]][:3]
    related += [q for q in posts if q is not p and q not in related][: 3 - len(related)]
    body = f'''<div class="wrap article-wrap">
<article>
  <header class="art-head">
    <div class="kicker">{pills}</div>
    <h1>{e(p["title"])}</h1>
    <p class="dek">{e(p["dek"])}</p>
    <div class="byline"><span>By <b>{e(p["author"])}</b></span><time datetime="{p["date"].isoformat()}">{fmt_time(p["date"])}</time><span class="bait-rating" title="Bait rating">Bait rating <span class="hooks">{hooks}</span></span></div>
  </header>
  {hero}
  {render_body(p)}
  {satire_note}
  {share(p)}
  {reactions(p)}
</article>
<aside>{most_baited(posts)}<div style="margin-top:32px">{ad(tall=True)}</div>{mini_week()}</aside>
</div>
<section class="keep"><div class="wrap">
  <div class="sec-head"><h2>Keep scrolling<small>We both know you're going to.</small></h2></div>
  <div class="grid-3">{"".join(card(q) for q in related)}</div>
</div></section>'''
    return layout(p["title"], body, path=p["url"], desc=p["dek"] or p["title"], og_type="article")


def advertise():
    body = f'''<section class="band red sec-hero"><div class="wrap">
  <h1>Advertise &amp; partner with B8ED</h1>
  <p>A satirical Irish media page covering sport, pop culture, politics and comedy. Quick, shareable posts built for scrolling, every day of the week.</p>
</div></section>
<div class="wrap page" style="padding-top:8px">
  <h2>What you get</h2>
  <div class="tiles">
    <div class="tile"><h3>Daily output</h3><p>New content every day. Each day has an owner, and owners bring in contributors from their own circle as we grow.</p></div>
    <div class="tile"><h3>A voice people share</h3><p>Satire aimed at bait culture itself, in the quick, shareable style Irish readers already scroll.</p></div>
    <div class="tile"><h3>An audience we own</h3><p>Competitions for concert and festival tickets grow our email list. Social brings readers in. The list keeps them.</p></div>
    <div class="tile"><h3>Within Irish law</h3><p>Everything published goes live through one editor experienced in engagement-driven content and advertising revenue.</p></div>
  </div>

  <h2>Signature segments</h2>
  <div class="tiles">
    <div class="tile ink"><h3>Baited Fake News</h3><p>Satirical headlines that parody the clickbait news cycle.</p></div>
    <div class="tile ink"><h3>Rage Bait</h3><p>Provocative posts that poke fun at outrage culture.</p></div>
    <div class="tile ink"><h3>Match-day vox pops</h3><p>Comedians interview fans before and after games at Croke Park, the Aviva and League of Ireland grounds.</p></div>
    <div class="tile ink"><h3>Live game updates</h3><p>Real-time match coverage that keeps readers on the page.</p></div>
    <div class="tile ink"><h3>Comedy night</h3><p>Clips and material from our monthly live night in Dublin.</p></div>
  </div>

  <h2 id="partner">Ways to partner</h2>
  <div class="tiles">
    <div class="tile red"><h3>Brands &amp; advertisers</h3><ul><li>Advertising space on the site</li><li>Brand features in our content</li><li>Larger brand deals as we grow</li></ul></div>
    <div class="tile red"><h3>Comedians &amp; creators</h3><ul><li>Open mic slots at the monthly night</li><li>Hosting match-day vox pops</li><li>A route to podcast appearances, including on Féach podcasts</li></ul></div>
    <div class="tile red"><h3>Venues &amp; event partners</h3><ul><li>Hosting the monthly comedy night</li><li>Concert and festival ticket prizes</li><li>Match-day access for vox pops</li></ul></div>
  </div>

  <h2>Where we're going</h2>
  <div class="tiles steps">
    <div class="tile"><h3>Promote our own content</h3><p>Build the audience and the content library.</p></div>
    <div class="tile"><h3>Sell advertising</h3><p>Advertising space on the site for third parties.</p></div>
    <div class="tile"><h3>Brand partnerships</h3><p>Larger deals that feature partner brands in our content.</p></div>
  </div>

  <h2>Let's talk</h2>
  <p>Brand, venue, comedian or would-be day owner, get in touch.</p>
  <a class="contact-big" href="mailto:{CONTACT}?subject=Partnering%20with%20B8ED">{CONTACT}</a>
</div>'''
    return layout("Advertise", body, path="/advertise/", desc="Advertise and partner with B8ED.ie, the satirical Irish media page for sport, pop culture, politics and comedy.")


def about():
    week = "".join(f'<div class="tile{" red" if c == "sport" else " ink" if c == "politics" else ""}"{" style=\"background:var(--red-deep);color:#fff\"" if c == "comedy" else ""}><h3>{d}</h3><p>{t}</p></div>' for d, t, c in WEEK)
    body = f'''<div class="wrap page">
  <h1>We play the engagement game. And laugh at it.</h1>
  <p class="lede">B8ED is a satirical Irish media page covering sport, pop culture, politics and comedy, in quick, shareable posts built for scrolling.</p>

  <h2>The week</h2>
  <div class="tiles" style="grid-template-columns:repeat(auto-fit,minmax(120px,1fr))">{week}</div>
  <p class="meta" style="margin-top:12px;font-size:.95rem">Every day has an owner. As the page grows, owners add a second post or bring in contributors from their own circle.</p>

  <h2 id="satire">Satire notice</h2>
  <div class="prose">
    <p>Anything marked <strong>SATIRE</strong> or filed under <a href="/fake-news/">Baited Fake News</a> is made up. The people in it are invented, the quotes are invented, and the committees are, sadly, probably real.</p>
    <p><a href="/rage-bait/">Rage Bait</a> pieces are deliberately provocative opinions written to poke fun at outrage culture. If one has you typing a reply in capital letters, it worked.</p>
    <p>Everything we publish stays within Irish law. If you think we've got something wrong, email <a href="mailto:{CONTACT}">{CONTACT}</a>.</p>
  </div>

  <h2 id="write">Write for us</h2>
  <div class="tiles">
    <div class="tile"><h3>Anonymous by design</h3><p>Work somewhere else in media? Write freely here, without the limits of your usual brand.</p></div>
    <div class="tile"><h3>Own a day</h3><p>Each day has an owner who shapes that day's content. Day owners are planned to hold a stake.</p></div>
    <div class="tile"><h3>Volunteer first</h3><p>Early contributions are voluntary. Payment follows revenue.</p></div>
    <div class="tile"><h3>Comedians</h3><p>Start at the open mic, host match-day vox pops, move on to podcasts.</p></div>
  </div>
  <p style="margin-top:20px">Pitch us: <a class="contact-big" style="font-size:1.4rem" href="mailto:{CONTACT}?subject=Writing%20for%20B8ED">{CONTACT}</a></p>
</div>'''
    return layout("About", body, path="/about/", desc="About B8ED.ie, the satirical Irish media page. Satire notice and how to write for us.")


def not_found():
    body = '''<div class="wrap page"><h1>404: You've been baited.</h1><p class="lede">This page doesn't exist. Much like the stories in our Fake News section.</p><p style="margin-top:24px"><a class="btn btn-red" href="/">Back to the homepage</a></p></div>'''
    return layout("Page not found", body, path="/404.html", desc="Page not found.")


def feed(posts):
    items = "".join(
        f"<item><title>{e(p['title'])}</title><link>{SITE}{p['url']}</link><guid>{SITE}{p['url']}</guid>"
        f"<pubDate>{p['date'].strftime('%a, %d %b %Y %H:%M:00 +0100')}</pubDate><description>{e(p['dek'])}</description></item>"
        for p in posts[:30])
    return (f'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>B8ED.ie</title>'
            f"<link>{SITE}/</link><description>Satirical Irish news, sport, pop culture, politics and comedy.</description>{items}</channel></rss>\n")


def sitemap(paths):
    urls = "".join(f"<url><loc>{SITE}{p}</loc></url>" for p in paths)
    return f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>\n'


def write(rel, text):
    path = ROOT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main():
    global TICKER, BUILD_DATE
    posts = load_posts()
    TICKER = posts[:8]
    BUILD_DATE = posts[0]["date"]
    for name in GENERATED:
        target = ROOT / name
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()

    paths = ["/"]
    write("index.html", home(posts))
    for key, (name, desc, when) in SECTIONS.items():
        tone = "ink" if key == "politics" else "deep" if key == "comedy" else "red"
        write(f"{key}/index.html", listing(name, desc, when, f"/{key}/", [p for p in posts if p["section"] == key], tone))
        paths.append(f"/{key}/")
    for seg, folder in SEGMENT_PATHS.items():
        name, desc, _ = SEGMENTS[seg]
        write(f"{folder}/index.html", listing(name, desc, "", f"/{folder}/", [p for p in posts if p["segment"] == seg], "ink" if seg == "rage-bait" else "red"))
        paths.append(f"/{folder}/")
    for p in posts:
        write(f"a/{p['slug']}/index.html", article(p, posts))
        paths.append(p["url"])
    write("advertise/index.html", advertise())
    write("about/index.html", about())
    write("404.html", not_found())
    write("feed.xml", feed(posts))
    write("sitemap.xml", sitemap(paths + ["/advertise/", "/about/"]))
    print(f"Built {len(posts)} posts, {len(paths) + 2} pages.")


TICKER, BUILD_DATE = [], dt.datetime.now()

if __name__ == "__main__":
    main()
