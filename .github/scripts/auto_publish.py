#!/usr/bin/env python3
"""
Auto-publish a fresh WildBreeze Field Guide briefing.

Runs from a GitHub Action every 2 days. Steps:
  1. Asks Claude (with web search enabled) to identify a currently-trending
     question that small/mid-size business owners are asking about AI
     adoption — specifically things that haven't already been covered by
     existing field-guide articles in this repo.
  2. Asks Claude to write the briefing in the WildBreeze house style.
  3. Slugifies, generates the HTML, writes it to field-guide/<slug>/index.html.
  4. Updates the field-guide/index.html article list (inserts new card at top).
  5. Updates sitemap.xml.
  6. The workflow commits + pushes everything.

Requires ANTHROPIC_API_KEY in env (from GitHub Actions secret).
"""
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from anthropic import Anthropic

ROOT = Path(__file__).resolve().parents[2]
FG = ROOT / "field-guide"
SITEMAP = ROOT / "sitemap.xml"

MODEL = "claude-sonnet-4-5"   # cheap, fast, plenty good for blog posts
client = Anthropic()  # picks up ANTHROPIC_API_KEY from env


# ============================================================
# Step 1+2: research the trending topic AND write the briefing
# in a single Claude call, with web search as a tool.
# ============================================================

def existing_slugs():
    return [p.name for p in FG.iterdir() if p.is_dir() and (p / "index.html").exists()]


def existing_titles():
    titles = []
    for p in FG.iterdir():
        if not p.is_dir():
            continue
        idx = p / "index.html"
        if not idx.exists():
            continue
        m = re.search(r"<title>([^<]+)</title>", idx.read_text())
        if m:
            titles.append(m.group(1).replace(" — WildBreeze", ""))
    return titles


SYSTEM_PROMPT = """You are the editor-in-chief of WildBreeze's Field Guide — a section of \
www.wildbreeze.io that publishes plain-English briefings for non-technical small and \
mid-size business owners about how to adopt AI in their operations safely and \
profitably.

Voice and style:
- Short, declarative, slightly understated. No hype words ("revolutionary",
  "transformative", "game-changing", "leverage", "synergy", "next-gen").
- Concrete over abstract. "The spreadsheet someone is maintaining at 11pm" beats
  "operational pain points."
- Past tense for actions completed; present tense for current advice.
- Numbers in JetBrains Mono in display contexts (we'll handle styling — you
  just write content).
- No emoji in headlines or body copy.
- Headlines split into two clauses, e.g. "Plain title. <em>Italic accent
  clause.</em>" Use a period or em-dash to split them.

Audience:
- Non-technical small-business operators (10-50 person companies).
- They run real operations, not technology companies. They want pragmatic
  advice, not vendor cheerleading.

Output discipline:
- Every article 700-1100 words.
- Use <h2> for major sections, <h3> for subsections.
- Use <ul>, <ol>, <code>, <pre>, <blockquote>, <strong> as appropriate.
- Always include 1-2 cross-links to existing field-guide articles where
  natural (you'll be told which exist).
- End with a brief "What we build" mention that links to /contact/.

Today's topic-selection criteria:
- It must be a question or topic that non-technical SMB owners are actually
  searching for or asking about RIGHT NOW (use web search to verify trending).
- It must NOT duplicate any existing article in the Field Guide (you'll be
  given the list).
- It must be specific enough to write a 700-1100 word answer, not so broad
  that the answer is "it depends."
- It must be operations-relevant (not a pure tech-enthusiast topic).
"""


def call_claude(existing_titles_str, today_iso):
    """Single call that does research + writes the article + returns JSON."""

    user_prompt = f"""Today is {today_iso}.

The Field Guide already has these articles (DO NOT duplicate):
{existing_titles_str}

Use web search to identify ONE trending question or topic that small/mid-size
business owners are currently searching for around adopting AI in their
operations. Then write a complete briefing on it.

Process:
1. Use web search 1-4 times to identify a trending topic.
2. Once you have your topic, write the article.
3. Output ONLY the JSON object below — no preamble, no commentary, no
   markdown fences, no "here's the article" text. Your entire final
   response must be a single parseable JSON object and nothing else.
   The script that consumes this response will fail if there is any
   text before the opening brace or after the closing brace.

Return your output as a single JSON object with this exact shape:

{{
  "slug": "kebab-case-url-slug-no-special-chars",
  "title": "The plain-text title",
  "title_html": "The headline split into a plain clause + a <span class=\\"accent\\">italic accent clause</span>",
  "description": "150-160 char meta description for SEO and link previews",
  "lede": "1-3 sentence opening paragraph that hooks the reader",
  "kicker": "BRIEFING NNN",
  "section": "Briefing",
  "date_iso": "{today_iso}",
  "date_human": "{datetime.now(timezone.utc).strftime('%-d %B %Y')}",
  "read_time": "X min read",
  "tags": ["3-6", "lowercase", "kebab-case", "tags"],
  "body": "<p>...full HTML article body, 700-1100 words, with h2/h3/ul/ol/code as appropriate. End with a horizontal rule and a 'Related' line linking to 1-2 existing articles by their /field-guide/<slug>/ paths...</p>"
}}

The "body" must be valid HTML, escaped properly inside the JSON string. Do not
include the <h1> title in the body — that's rendered separately. Do start with
a <p> opening paragraph that picks up where the lede left off.

Pick a "BRIEFING NNN" number that's higher than any in the existing-article list
(currently the highest is 003)."""

    resp = client.messages.create(
        model=MODEL,
        max_tokens=8000,
        system=SYSTEM_PROMPT,
        tools=[{
            "type": "web_search_20250305",
            "name": "web_search",
            "max_uses": 5,
        }],
        messages=[{"role": "user", "content": user_prompt}],
    )

    # Extract all text content (skipping tool_use / tool_result blocks).
    # When web_search is used, Claude often interleaves narration with the
    # final JSON. Some block types (server_tool_use, web_search_tool_result)
    # may have a `.text` attribute that is None — filter those out by type
    # check, not just hasattr.
    text_blocks = []
    for b in resp.content:
        t = getattr(b, "text", None)
        if isinstance(t, str) and t.strip():
            text_blocks.append(t)
    if not text_blocks:
        # Surface what we did get so we can debug
        block_types = [getattr(b, "type", type(b).__name__) for b in resp.content]
        raise RuntimeError(f"No text blocks in Claude response. Block types: {block_types}")
    full_text = "\n".join(text_blocks).strip()

    # Strip ``` fences anywhere in the text (model may wrap json in fences).
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", full_text, re.DOTALL)
    if fenced:
        candidate = fenced.group(1)
    else:
        # No fences — find the first balanced JSON object in the text by
        # walking braces. Naive approach: locate first `{` that begins a
        # parsable object. Try progressively larger spans until json.loads
        # succeeds, starting from each `{` position.
        candidate = None
        for start in [m.start() for m in re.finditer(r"\{", full_text)]:
            # Track brace depth starting from this `{`
            depth = 0
            for i in range(start, len(full_text)):
                c = full_text[i]
                if c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        chunk = full_text[start:i+1]
                        try:
                            json.loads(chunk)
                            candidate = chunk
                            break
                        except json.JSONDecodeError:
                            break  # this `{` didn't start a valid object — try the next one
            if candidate:
                break

    if not candidate:
        # Last resort: dump the raw text to stderr so the workflow run
        # surfaces what Claude actually returned, then re-raise.
        print("ERR: could not extract JSON from Claude response.", file=sys.stderr)
        print("=== RAW RESPONSE START ===", file=sys.stderr)
        print(full_text[:4000], file=sys.stderr)
        print("=== RAW RESPONSE END ===", file=sys.stderr)
        raise RuntimeError("No parsable JSON found in Claude response")

    return json.loads(candidate)


# ============================================================
# Step 3+4+5: render HTML + update index + sitemap
# ============================================================

def slugify(s):
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:60]


def render_article_html(slug, data):
    """Inline mini-template — kept self-contained so the workflow doesn't
    depend on importing _gen_article.py from the repo root."""
    tags = data.get("tags", [])
    tag_meta = "\n".join(f'<meta property="article:tag" content="{t}" />' for t in tags)
    keywords = ", ".join(tags)

    # Pick 2 related articles (most recent that aren't this one)
    related = []
    for p in sorted(FG.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
        if not p.is_dir() or p.name == slug:
            continue
        idx = p / "index.html"
        if not idx.exists():
            continue
        h = idx.read_text()
        title = re.search(r"<title>([^<]+) — WildBreeze</title>", h)
        desc = re.search(r'name="description" content="([^"]+)"', h)
        date = re.search(r'<time datetime="([^"]+)">', h)
        kicker = re.search(r'class="kicker"[^>]*>([^<]+)<', h)
        if title and desc:
            related.append({
                "slug": p.name,
                "title": title.group(1),
                "description": desc.group(1),
                "date_iso": date.group(1) if date else "",
                "kicker": kicker.group(1).strip() if kicker else "Field Guide",
            })
        if len(related) >= 2:
            break

    related_html = ""
    for r in related:
        related_html += f"""      <a class="article-card" href="/field-guide/{r['slug']}/">
        <div class="meta">
          <span class="date">{r['date_iso']}</span>
          <span>{r['kicker']}</span>
        </div>
        <div class="body">
          <h3>{r['title']}</h3>
          <p>{r['description']}</p>
          <span class="read-more">READ →</span>
        </div>
      </a>
"""

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{data['title']} — WildBreeze</title>
<meta name="description" content="{data['description']}" />
<link rel="canonical" href="https://www.wildbreeze.io/field-guide/{slug}/" />
<meta name="theme-color" content="#06080F" />
<meta property="og:title" content="{data['title']}" />
<meta property="og:description" content="{data['description']}" />
<meta property="og:type" content="article" />
<meta property="og:url" content="https://www.wildbreeze.io/field-guide/{slug}/" />
<meta property="og:image" content="https://www.wildbreeze.io/og-preview.png" />
<meta property="og:image:width" content="1200" />
<meta property="og:image:height" content="630" />
<meta property="article:published_time" content="{data['date_iso']}" />
<meta property="article:section" content="{data.get('section','Briefing')}" />
{tag_meta}
<meta name="twitter:card" content="summary_large_image" />
<meta name="twitter:image" content="https://www.wildbreeze.io/og-preview.png" />
<link rel="icon" type="image/svg+xml" href="/favicon.svg" />
<link rel="icon" type="image/png" sizes="32x32" href="/favicon-32.png" />
<link rel="apple-touch-icon" sizes="180x180" href="/favicon-180.png" />
<link rel="preconnect" href="https://fonts.googleapis.com" />
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;500;600;700&family=Inter:wght@300;400;500;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet" />
<link rel="stylesheet" href="/wb-style.css" />
<script type="application/ld+json">
{{
  "@context": "https://schema.org",
  "@type": "Article",
  "headline": {json.dumps(data['title'])},
  "description": {json.dumps(data['description'])},
  "datePublished": "{data['date_iso']}",
  "dateModified": "{data['date_iso']}",
  "author": {{ "@type": "Organization", "name": "WildBreeze", "url": "https://www.wildbreeze.io/" }},
  "publisher": {{ "@type": "Organization", "name": "WildBreeze", "url": "https://www.wildbreeze.io/", "logo": {{ "@type": "ImageObject", "url": "https://www.wildbreeze.io/favicon-512.png" }} }},
  "image": "https://www.wildbreeze.io/og-preview.png",
  "mainEntityOfPage": {{ "@type": "WebPage", "@id": "https://www.wildbreeze.io/field-guide/{slug}/" }},
  "keywords": {json.dumps(keywords)}
}}
</script>
</head>
<body>

<div class="field" aria-hidden="true"></div>
<div class="grid" aria-hidden="true"></div>

<header class="nav">
  <div class="wrap row">
    <a href="/" class="logo">
      <svg class="mark" viewBox="0 0 36 18" aria-hidden="true">
        <defs><linearGradient id="wb-mark-grad" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stop-color="#5EF2FF"/><stop offset="55%" stop-color="#A78BFA"/><stop offset="100%" stop-color="#5EF2FF"/>
        </linearGradient></defs>
        <path d="M-8 9 q 2 -6 4 0 t 4 0 t 4 0 t 4 0 t 4 0 t 4 0 t 4 0 t 4 0 t 4 0 t 4 0 t 4 0 t 4 0"
              fill="none" stroke="url(#wb-mark-grad)" stroke-width="1.8"
              stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
      <span>WildBreeze</span>
    </a>
    <nav class="main">
      <a href="/#services">Services</a>
      <a href="/field-guide/">Field Guide</a>
      <a href="/contact/" class="cta">Contact</a>
    </nav>
  </div>
</header>

<article>
  <section class="page-hero">
    <div class="wrap prose">
      <div class="kicker">{data['kicker']}</div>
      <h1 class="page-title">{data.get('title_html', data['title'])}</h1>
      <p class="lede">{data['lede']}</p>
      <div class="article-meta">
        <span><time datetime="{data['date_iso']}">{data['date_human']}</time></span>
        <span>{data.get('read_time', '7 min read')}</span>
        {' '.join(f'<span class="tag">#{t}</span>' for t in tags)}
      </div>
    </div>
  </section>

  <section class="prose-body">
    <div class="wrap prose">
{data['body']}
    </div>
  </section>
</article>

<section class="section" style="border-top: 1px solid var(--line);">
  <div class="wrap prose">
    <div class="section-head">
      <div class="kicker">Keep reading</div>
      <h2 style="font-size: 28px;">More from the Field Guide</h2>
    </div>
    <div class="articles">
{related_html}
    </div>
  </div>
</section>

<footer class="site">
  <div class="wrap">
    <div class="row">
      <div>
        <a href="/" class="logo">
          <svg class="mark" viewBox="0 0 36 18" aria-hidden="true">
            <defs><linearGradient id="wb-mark-grad-f" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" stop-color="#5EF2FF"/><stop offset="55%" stop-color="#A78BFA"/><stop offset="100%" stop-color="#5EF2FF"/>
            </linearGradient></defs>
            <path d="M-8 9 q 2 -6 4 0 t 4 0 t 4 0 t 4 0 t 4 0 t 4 0 t 4 0 t 4 0 t 4 0 t 4 0 t 4 0 t 4 0"
                  fill="none" stroke="url(#wb-mark-grad-f)" stroke-width="1.8"
                  stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
          <span>WildBreeze</span>
        </a>
        <p class="blurb">Quiet automation infrastructure for operations run by humans.</p>
      </div>
      <div class="meta">
        <div class="col"><h5>Build</h5><a href="/#services">Custom MCP servers</a><a href="/#services">Scheduled agents</a><a href="/#services">Weekly reports</a></div>
        <div class="col"><h5>Learn</h5><a href="/field-guide/agents/">What is an agent?</a><a href="/field-guide/mcp-servers/">What is an MCP server?</a><a href="/field-guide/#articles">All briefings</a></div>
        <div class="col"><h5>Contact</h5><a href="/contact/">Contact form</a><a href="mailto:hello@wildbreeze.io">hello@wildbreeze.io</a></div>
      </div>
    </div>
    <div class="legal">
      <div>© 2026 WildBreeze. All systems quiet.</div>
      <div>Built by <a href="https://www.napier.me" class="link" target="_blank" rel="noopener">napier.me</a></div>
    </div>
  </div>
</footer>

</body>
</html>
"""


def update_field_guide_index(slug, data):
    """Insert a new article card into field-guide/index.html article list."""
    idx_path = FG / "index.html"
    html = idx_path.read_text()

    new_card = f"""      <a class="article-card reveal" href="/field-guide/{slug}/">
        <div class="meta">
          <span class="date">{data['date_iso']}</span>
          <span>{data['kicker']}</span>
          <span>{data.get('read_time', '7 min read')}</span>
        </div>
        <div class="body">
          <h3>{data['title']}</h3>
          <p>{data['description']}</p>
          <span class="read-more">READ →</span>
        </div>
      </a>

"""

    # Insert after the marker comment
    marker = "<!-- AUTO-GENERATED ARTICLES INSERTED ABOVE THIS LINE BY THE WORKFLOW -->"
    if marker not in html:
        # Fallback: insert at start of #article-list
        html = html.replace('<div class="articles" id="article-list">',
                            f'<div class="articles" id="article-list">\n{new_card}',
                            1)
    else:
        # Insert ABOVE the marker (which sits ABOVE the existing cards), so newest is on top
        html = html.replace(marker, f"{new_card}      {marker}", 1)

    idx_path.write_text(html)
    print(f"OK updated {idx_path.relative_to(ROOT)}")


def update_sitemap(slug, data):
    """Add new article URL to sitemap.xml."""
    text = SITEMAP.read_text()
    entry = f"""  <url>
    <loc>https://www.wildbreeze.io/field-guide/{slug}/</loc>
    <lastmod>{data['date_iso']}</lastmod>
    <changefreq>monthly</changefreq>
    <priority>0.7</priority>
  </url>
"""
    if f"/field-guide/{slug}/" in text:
        print(f"info: {slug} already in sitemap, skipping")
        return
    text = text.replace("</urlset>", f"{entry}</urlset>")
    SITEMAP.write_text(text)
    print(f"OK updated sitemap.xml")


# ============================================================
# main
# ============================================================

def main():
    today_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    titles = existing_titles()
    titles_str = "\n".join(f"  - {t}" for t in titles)
    print(f"Existing articles:\n{titles_str}\n")

    print("Calling Claude with web search…")
    data = call_claude(titles_str, today_iso)

    slug = slugify(data.get("slug", "") or data["title"])
    if not slug:
        print("ERR: empty slug from Claude", file=sys.stderr)
        sys.exit(1)

    target_dir = FG / slug
    if target_dir.exists():
        print(f"info: {slug} already exists — Claude picked a duplicate. Skipping.")
        return

    target_dir.mkdir(parents=True)
    target = target_dir / "index.html"
    target.write_text(render_article_html(slug, data))
    print(f"OK wrote {target.relative_to(ROOT)}")

    update_field_guide_index(slug, data)
    update_sitemap(slug, data)


if __name__ == "__main__":
    main()
