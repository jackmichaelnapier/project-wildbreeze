#!/usr/bin/env python3
"""
Auto-publish a fresh WildBreeze Field Guide briefing — English + Spanish.

Runs from a GitHub Action every 2 days. Steps:
  1. English: Claude identifies a trending small-business AI topic (web search),
     writes a briefing, returns structured JSON.
  2. English: render HTML, write to field-guide/<slug>/, update index, sitemap.
  3. Spanish: Claude translates and localizes the same article to native
     Castilian Spanish, returns structured JSON.
  4. Spanish: render HTML, write to es/guia-de-campo/<spanish-slug>/, update
     Spanish index, sitemap.

Requires ANTHROPIC_API_KEY in env (GitHub Actions secret).
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
ES_FG = ROOT / "es" / "guia-de-campo"
SITEMAP = ROOT / "sitemap.xml"

MODEL = "claude-sonnet-4-5"
client = Anthropic()


# ============================================================
# Helpers
# ============================================================

def slugify(s):
    s = s.lower().strip()
    s = re.sub(r"[áàä]", "a", s)
    s = re.sub(r"[éèë]", "e", s)
    s = re.sub(r"[íìï]", "i", s)
    s = re.sub(r"[óòö]", "o", s)
    s = re.sub(r"[úùü]", "u", s)
    s = re.sub(r"[ñ]", "n", s)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:60]


def existing_titles(directory):
    titles = []
    if not directory.exists():
        return titles
    for p in directory.iterdir():
        if not p.is_dir():
            continue
        idx = p / "index.html"
        if not idx.exists():
            continue
        m = re.search(r"<title>([^<]+)</title>", idx.read_text())
        if m:
            t = m.group(1).replace(" — WildBreeze", "").replace(" · WildBreeze", "")
            titles.append(t)
    return titles


def extract_json_from_response(resp):
    """Extract JSON from Claude response, robust to narration text."""
    text_blocks = []
    for b in resp.content:
        t = getattr(b, "text", None)
        if isinstance(t, str) and t.strip():
            text_blocks.append(t)
    if not text_blocks:
        block_types = [getattr(b, "type", type(b).__name__) for b in resp.content]
        raise RuntimeError(f"No text blocks. Block types: {block_types}")
    full_text = "\n".join(text_blocks).strip()

    # Try fenced
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", full_text, re.DOTALL)
    if fenced:
        return json.loads(fenced.group(1))

    # Walk braces to find first balanced JSON object
    for start in [m.start() for m in re.finditer(r"\{", full_text)]:
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
                        return json.loads(chunk)
                    except json.JSONDecodeError:
                        break

    print("ERR: could not extract JSON. Raw response:", file=sys.stderr)
    print(full_text[:4000], file=sys.stderr)
    raise RuntimeError("No parsable JSON in Claude response")


# ============================================================
# Step 1: English article generation (web search)
# ============================================================

EN_SYSTEM = """You are the editor-in-chief of WildBreeze's Field Guide — a section of \
www.wildbreeze.io that publishes plain-English briefings for non-technical small and \
mid-size business owners about how to adopt AI in their operations safely and \
profitably.

Voice and style:
- Short, declarative, slightly understated. No hype words.
- Concrete over abstract. "The spreadsheet someone is maintaining at 11pm" beats
  "operational pain points."
- Past tense for actions completed; present tense for current advice.
- No emoji in headlines or body copy.
- Headlines split into two clauses with a period, second clause is the
  italic accent.
- AVOID em-dashes (—) entirely. Use periods, commas, parentheses, or colons.
- Avoid AI-tells: "delve into", "leverage", "robust", "transformative",
  "revolutionary", "navigate the complexities", "in today's world", etc.

Audience: non-technical small-business operators (10-50 person companies)."""


def generate_en_article(today_iso):
    titles = existing_titles(FG)
    titles_str = "\n".join(f"  - {t}" for t in titles)
    print(f"Existing EN articles:\n{titles_str}\n", file=sys.stderr)

    prompt = f"""Today is {today_iso}.

The Field Guide already has these articles (DO NOT duplicate):
{titles_str}

Process:
1. Use web search 1-4 times to identify a trending question or topic that
   small/mid-size business owners are currently asking about adopting AI in
   their operations. Verify recency by checking dates of search results.
2. Once you have your topic, write a complete briefing.
3. Output ONLY the JSON object below — no preamble, no commentary, no
   markdown fences, no "here's the article" text.

Return as a single JSON object:

{{
  "slug": "kebab-case-url-slug",
  "title": "The plain-text title",
  "title_html": "Plain clause. <span class=\\"accent\\">Italic accent clause.</span>",
  "description": "150-160 char meta description for SEO",
  "lede": "1-3 sentence opening paragraph",
  "kicker": "BRIEFING NNN",
  "section": "Briefing",
  "date_iso": "{today_iso}",
  "date_human": "{datetime.now(timezone.utc).strftime('%-d %B %Y')}",
  "read_time": "X min read",
  "tags": ["3-6", "lowercase", "kebab-case", "tags"],
  "body": "<p>...full HTML article body, 700-1100 words, with h2/h3/ul/ol/code as appropriate. End with a horizontal rule and a 'Related' line linking to 1-2 existing articles by their /field-guide/<slug>/ paths...</p>"
}}

Pick a "BRIEFING NNN" higher than any existing. The "body" must be valid HTML
escaped properly inside the JSON string. AVOID em-dashes."""

    resp = client.messages.create(
        model=MODEL,
        max_tokens=8000,
        system=EN_SYSTEM,
        tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 5}],
        messages=[{"role": "user", "content": prompt}],
    )
    return extract_json_from_response(resp)


# ============================================================
# Step 2: Spanish translation/localization (no web search)
# ============================================================

ES_SYSTEM = """Eres el editor en jefe de la edición en español de la Guía de Campo \
de WildBreeze (www.wildbreeze.io/es/), publicaciones para dueños de pequeños y \
medianos negocios no técnicos sobre cómo adoptar IA en sus operaciones.

Voz y estilo:
- Cortos, declarativos, ligeramente moderados. Sin palabras de hype.
- Concreto sobre abstracto. "La hoja de cálculo que alguien mantiene a las 23h"
  gana a "puntos de dolor operativos".
- Tutea al lector ("tú", "te", "tu") en lugar de usar "usted".
- Sin emojis en titulares ni en cuerpo.
- Titulares partidos en dos cláusulas con punto, la segunda es el acento itálico.
- EVITA las rayas largas (—) por completo. Usa puntos, comas, paréntesis o dos puntos.
- Castellano de España (no español neutro), pero comprensible para hispanohablantes
  de Latinoamérica.

Audiencia: operadores no técnicos de empresas pequeñas (10 a 50 personas) en
España y América Latina."""


def translate_to_es(en_article):
    """Translate the English article to native-Spanish for a Spanish SMB audience."""
    titles = existing_titles(ES_FG)
    titles_str = "\n".join(f"  - {t}" for t in titles)
    print(f"Existing ES articles:\n{titles_str}\n", file=sys.stderr)

    en_json = json.dumps(en_article, ensure_ascii=False)

    prompt = f"""Aquí va el artículo en inglés que acabamos de publicar:

{en_json}

Tradúcelo a español castellano nativo, NO traducción literal. Debe sonar
escrito por un hablante nativo, no traducido. Adapta los ejemplos donde tenga
sentido (€ en lugar de $, ejemplos europeos cuando aplique). Conserva la
estructura HTML del cuerpo, pero traduce el texto. Mantén el "kicker" en formato
"INFORME NNN" (no "BRIEFING").

Devuelve SOLO el objeto JSON con esta forma exacta. No añadas preámbulo ni
comentario. La respuesta entera debe ser un único JSON parseable.

{{
  "slug": "slug-en-espanol-sin-acentos",
  "title": "Titulo en espanol (sin entidades HTML)",
  "title_html": "Clausula plana. <span class=\\"accent\\">Clausula acento.</span>",
  "description": "Descripcion meta 150-160 caracteres",
  "lede": "Lede en espanol",
  "kicker": "INFORME NNN",
  "section": "Informe",
  "date_iso": "{en_article['date_iso']}",
  "date_human": "{en_article['date_human']}",
  "read_time": "X min de lectura",
  "tags": ["tags", "en", "espanol", "kebab-case"],
  "body": "<p>... cuerpo HTML traducido. Cambia rutas /field-guide/ por /es/guia-de-campo/ en los enlaces 'Related' al final ...</p>"
}}

Los slugs existentes en español son:
{titles_str}

NO dupliques uno. EVITA las rayas largas (—) en el cuerpo."""

    resp = client.messages.create(
        model=MODEL,
        max_tokens=8000,
        system=ES_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    return extract_json_from_response(resp)


# ============================================================
# Render templates
# ============================================================

def render_article(slug, data, lang, other_slug=None):
    is_es = (lang == "es")
    base = "/es/guia-de-campo" if is_es else "/field-guide"
    other_base = "/field-guide" if is_es else "/es/guia-de-campo"
    site_base = "https://www.wildbreeze.io"
    article_url = f"{site_base}{base}/{slug}/"
    # If we know the OTHER language's slug, use it for the cross-language URL.
    # Falling back to same slug only happens when render is called for one
    # language without the other (legacy / future single-lang call).
    cross_slug = other_slug if other_slug else slug
    other_url = f"{site_base}{other_base}/{cross_slug}/"
    home = "/es/" if is_es else "/"

    tags = data.get("tags", [])
    tag_meta = "\n".join(f'<meta property="article:tag" content="{t}" />' for t in tags)

    nav_links = (
        '<a href="/es/#servicios">Servicios</a><a href="/es/guia-de-campo/">Guía de campo</a><a href="/es/sobre/">Sobre</a><a href="/es/contacto/" class="cta">Contacto</a>'
        if is_es else
        '<a href="/#services">Services</a><a href="/field-guide/">Field Guide</a><a href="/about/">About</a><a href="/contact/" class="cta">Contact</a>'
    )
    keep_reading = "Más de la Guía" if is_es else "More from the Field Guide"
    keep_reading_kicker = "Sigue leyendo" if is_es else "Keep reading"
    blurb = "Infraestructura de automatización silenciosa para operaciones humanas." if is_es else "Quiet automation infrastructure for operations run by humans."
    legal = "© 2026 WildBreeze. Todos los sistemas en silencio." if is_es else "© 2026 WildBreeze. All systems quiet."
    builtby = "Hecho por" if is_es else "Built by"

    # Footer columns
    footer_cols_es = '''<div class="col"><h5>Construir</h5><a href="/es/#servicios">Servidores MCP</a><a href="/es/#servicios">Agentes programados</a><a href="/es/#servicios">Informes semanales</a></div>
        <div class="col"><h5>Aprender</h5><a href="/es/guia-de-campo/">Guía de campo</a><a href="/es/glosario/">Glosario</a><a href="/es/calculadora/">Calculadora</a><a href="/es/sobre/">Sobre</a></div>
        <div class="col"><h5>Contacto</h5><a href="/es/contacto/">Formulario</a><a href="mailto:hello@wildbreeze.io">hello@wildbreeze.io</a></div>'''
    footer_cols_en = '''<div class="col"><h5>Build</h5><a href="/#services">Custom MCP servers</a><a href="/#services">Scheduled agents</a><a href="/#services">Weekly reports</a></div>
        <div class="col"><h5>Learn</h5><a href="/field-guide/">Field Guide</a><a href="/glossary/">Glossary</a><a href="/calculator/">Cost calculator</a><a href="/about/">About</a></div>
        <div class="col"><h5>Contact</h5><a href="/contact/">Contact form</a><a href="mailto:hello@wildbreeze.io">hello@wildbreeze.io</a></div>'''
    footer_cols = footer_cols_es if is_es else footer_cols_en

    # Pick 2 related articles
    fg_dir = ES_FG if is_es else FG
    related = []
    if fg_dir.exists():
        for p in sorted(fg_dir.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
            if not p.is_dir() or p.name == slug:
                continue
            idx = p / "index.html"
            if not idx.exists():
                continue
            h = idx.read_text()
            t = re.search(r"<title>([^<]+) (?:—|·) WildBreeze</title>", h)
            d = re.search(r'name="description" content="([^"]+)"', h)
            dt = re.search(r'<time datetime="([^"]+)">', h)
            kk = re.search(r'class="kicker"[^>]*>([^<]+)<', h)
            if t and d:
                related.append({
                    "slug": p.name,
                    "title": t.group(1),
                    "description": d.group(1),
                    "date_iso": dt.group(1) if dt else "",
                    "kicker": kk.group(1).strip() if kk else "",
                })
            if len(related) >= 2:
                break

    related_html = ""
    for r in related:
        read_label = "LEER →" if is_es else "READ →"
        related_html += f'''      <a class="article-card" href="{base}/{r["slug"]}/">
        <div class="meta"><span class="date">{r["date_iso"]}</span><span>{r["kicker"]}</span></div>
        <div class="body"><h3>{r["title"]}</h3><p>{r["description"]}</p><span class="read-more">{read_label}</span></div>
      </a>
'''

    return f"""<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{data['title']} {('·' if is_es else '—')} WildBreeze</title>
<meta name="description" content="{data['description']}" />
<link rel="canonical" href="{article_url}" />
<meta name="theme-color" content="#06080F" />
<meta property="og:title" content="{data['title']}" />
<meta property="og:description" content="{data['description']}" />
<meta property="og:type" content="article" />
<meta property="og:url" content="{article_url}" />
<meta property="og:image" content="{site_base}/og-preview.png" />
<meta property="og:image:width" content="1200" />
<meta property="og:image:height" content="630" />
{('<meta property="og:locale" content="es_ES" />' if is_es else '')}
<meta property="article:published_time" content="{data['date_iso']}" />
<meta property="article:section" content="{data.get('section','Field Guide' if not is_es else 'Guía de campo')}" />
{tag_meta}
<meta name="twitter:card" content="summary_large_image" />
<meta name="twitter:image" content="{site_base}/og-preview.png" />
<link rel="alternate" hreflang="{'es' if is_es else 'en'}" href="{article_url}" />
<link rel="alternate" hreflang="{'en' if is_es else 'es'}" href="{other_url}" />
<!-- WB-TAGS-START -->
<!-- Google tag (gtag.js) — GA4 G-4S960N841V -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-4S960N841V"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){{dataLayer.push(arguments);}}
  gtag('js', new Date());
  gtag('config', 'G-4S960N841V');
</script>
<!-- WB-TAGS-END -->
<link rel="icon" type="image/svg+xml" href="/favicon.svg" />
<link rel="icon" type="image/png" sizes="32x32" href="/favicon-32.png" />
<link rel="apple-touch-icon" sizes="180x180" href="/favicon-180.png" />
<link rel="preconnect" href="https://fonts.googleapis.com" />
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;500;600;700&family=Inter:wght@300;400;500;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet" />
<link rel="stylesheet" href="/wb-style.css" />
<style>
  .lang-toggle {{ font-family: var(--mono); font-size: 12px; color: var(--ink-3); letter-spacing: 0.08em; margin-left: 16px; }}
  .lang-toggle a {{ color: var(--cyan); padding: 0 4px; }}
  .lang-toggle .sep {{ color: var(--line-2); }}
  .lang-toggle .active {{ color: var(--ink); }}
  /* WB-CLIENT-CSS-START */
  /* Client area pill (footer .legal) — managed by _inject_client_link.py */
  .client-link {{
    display: inline-flex; align-items: center; gap: 6px;
    font-family: var(--mono); font-size: 11px;
    letter-spacing: 0.08em; text-transform: uppercase;
    color: var(--ink-2);
    border: 1px solid var(--line-2);
    border-radius: 999px;
    padding: 6px 14px;
    text-decoration: none;
    transition: all 180ms ease;
  }}
  .client-link:hover {{
    color: var(--cyan);
    border-color: rgba(94, 242, 255, 0.5);
    background: rgba(94, 242, 255, 0.04);
  }}
  .client-link .arrow {{ color: var(--cyan); transition: transform 180ms ease; }}
  .client-link:hover .arrow {{ transform: translateX(3px); }}
  /* WB-CLIENT-CSS-END */
</style>
<script type="application/ld+json">
{{
  "@context": "https://schema.org",
  "@type": "Article",
  "headline": {json.dumps(data['title'])},
  "description": {json.dumps(data['description'])},
  "datePublished": "{data['date_iso']}",
  "dateModified": "{data['date_iso']}",
  "inLanguage": "{lang}",
  "author": {{ "@type": "Organization", "name": "WildBreeze", "url": "https://www.wildbreeze.io/" }},
  "publisher": {{ "@type": "Organization", "name": "WildBreeze", "url": "https://www.wildbreeze.io/", "logo": {{ "@type": "ImageObject", "url": "https://www.wildbreeze.io/favicon-512.png" }} }},
  "image": "https://www.wildbreeze.io/og-preview.png",
  "mainEntityOfPage": {{ "@type": "WebPage", "@id": "{article_url}" }},
  "keywords": {json.dumps(", ".join(tags))}
}}
</script>
</head>
<body>

<div class="field" aria-hidden="true"></div>
<div class="grid" aria-hidden="true"></div>

<header class="nav">
  <div class="wrap row">
    <a href="{home}" class="logo">
      <svg class="mark" viewBox="0 0 36 18" aria-hidden="true">
        <defs><linearGradient id="wb-mark-grad" x1="0" y1="0" x2="1" y2="0"><stop offset="0%" stop-color="#5EF2FF"/><stop offset="55%" stop-color="#A78BFA"/><stop offset="100%" stop-color="#5EF2FF"/></linearGradient></defs>
        <path d="M-8 9 q 2 -6 4 0 t 4 0 t 4 0 t 4 0 t 4 0 t 4 0 t 4 0 t 4 0 t 4 0 t 4 0 t 4 0 t 4 0" fill="none" stroke="url(#wb-mark-grad)" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
      <span>WildBreeze</span>
    </a>
    <nav class="main">
      {nav_links}
      <span class="lang-toggle">{('<a href="' + other_url + '" hreflang="en">EN</a><span class="sep">·</span><span class="active">ES</span>') if is_es else ('<span class="active">EN</span><span class="sep">·</span><a href="' + other_url + '" hreflang="es">ES</a>')}</span>
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
        <span>{data.get('read_time', '7 min read' if not is_es else '7 min de lectura')}</span>
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
      <div class="kicker">{keep_reading_kicker}</div>
      <h2 style="font-size: 28px;">{keep_reading}</h2>
    </div>
    <div class="articles">
{related_html}    </div>
  </div>
</section>

<footer class="site">
  <div class="wrap">
    <div class="row">
      <div>
        <a href="{home}" class="logo">
          <svg class="mark" viewBox="0 0 36 18" aria-hidden="true">
            <defs><linearGradient id="wb-mark-grad-f" x1="0" y1="0" x2="1" y2="0"><stop offset="0%" stop-color="#5EF2FF"/><stop offset="55%" stop-color="#A78BFA"/><stop offset="100%" stop-color="#5EF2FF"/></linearGradient></defs>
            <path d="M-8 9 q 2 -6 4 0 t 4 0 t 4 0 t 4 0 t 4 0 t 4 0 t 4 0 t 4 0 t 4 0 t 4 0 t 4 0 t 4 0" fill="none" stroke="url(#wb-mark-grad-f)" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
          <span>WildBreeze</span>
        </a>
        <p class="blurb">{blurb}</p>
      </div>
      <div class="meta">
        {footer_cols}
      </div>
    </div>
    <div class="legal">
      <div>{legal}</div>
      <!-- WB-CLIENT-HTML-START --><a class="client-link" href="/account/">{('Área cliente' if is_es else 'Client area')} <span class="arrow">→</span></a><!-- WB-CLIENT-HTML-END -->
      <div>{builtby} <a href="https://www.napier.me" class="link" target="_blank" rel="noopener">napier.me</a></div>
    </div>
  </div>
</footer>

</body>
</html>
"""


# ============================================================
# Update field-guide index page (insert new card at top)
# ============================================================

def update_index(slug, data, lang):
    is_es = (lang == "es")
    fg_dir = ES_FG if is_es else FG
    idx_path = fg_dir / "index.html"
    if not idx_path.exists():
        print(f"  warn: {idx_path} doesn't exist, can't update", file=sys.stderr)
        return
    html = idx_path.read_text()

    base = "/es/guia-de-campo" if is_es else "/field-guide"
    read_label = "LEER →" if is_es else "READ →"
    read_time = data.get("read_time", "7 min read" if not is_es else "7 min de lectura")

    new_card = f'''      <a class="article-card" href="{base}/{slug}/">
        <div class="meta">
          <span class="date">{data['date_iso']}</span>
          <span>{data['kicker']}</span>
          <span>{read_time}</span>
        </div>
        <div class="body">
          <h3>{data['title']}</h3>
          <p>{data['description']}</p>
          <span class="read-more">{read_label}</span>
        </div>
      </a>

'''
    marker = "<!-- AUTO-GENERATED ARTICLES INSERTED ABOVE THIS LINE BY THE WORKFLOW -->"
    if marker in html:
        html = html.replace(marker, f"{new_card}      {marker}", 1)
    else:
        html = html.replace('<div class="articles" id="article-list">',
                            f'<div class="articles" id="article-list">\n{new_card}', 1)
    idx_path.write_text(html)
    print(f"  updated {idx_path.relative_to(ROOT)}")


# ============================================================
# Update sitemap.xml
# ============================================================

def update_sitemap(slug, data, lang):
    is_es = (lang == "es")
    base = "/es/guia-de-campo" if is_es else "/field-guide"
    text = SITEMAP.read_text()
    url = f"https://www.wildbreeze.io{base}/{slug}/"
    if url in text:
        return
    entry = f'''  <url>
    <loc>{url}</loc>
    <lastmod>{data['date_iso']}</lastmod>
    <changefreq>monthly</changefreq>
    <priority>0.7</priority>
  </url>
'''
    text = text.replace("</urlset>", f"{entry}</urlset>")
    SITEMAP.write_text(text)
    print(f"  updated sitemap.xml ({lang})")


# ============================================================
# main
# ============================================================

def write_article(data, lang, other_slug=None):
    slug = slugify(data.get("slug", "") or data["title"])
    if not slug:
        raise RuntimeError(f"empty slug for {lang}")

    fg_dir = ES_FG if lang == "es" else FG
    target = fg_dir / slug
    if target.exists():
        print(f"  info: {lang}/{slug} already exists, skipping write")
        return slug

    target.mkdir(parents=True)
    (target / "index.html").write_text(render_article(slug, data, lang, other_slug))
    print(f"  wrote {target.relative_to(ROOT)}/index.html")
    update_index(slug, data, lang)
    update_sitemap(slug, data, lang)
    return slug


def main():
    today_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # 1. English article
    print("=== EN: generating with web search ===", file=sys.stderr)
    en = generate_en_article(today_iso)
    en_slug = slugify(en.get("slug", "") or en["title"])

    # 2. Spanish translation/localization
    print("=== ES: translating ===", file=sys.stderr)
    es = translate_to_es(en)
    # Force Spanish date_iso to match
    es["date_iso"] = en["date_iso"]
    es["date_human"] = en["date_human"]
    es_slug = slugify(es.get("slug", "") or es["title"])

    # 3. Now write BOTH, passing each other's slug for correct cross-language hreflang
    print(f"=== writing both: en={en_slug}  es={es_slug} ===", file=sys.stderr)
    en_slug = write_article(en, "en", other_slug=es_slug)
    print(f"OK EN: {en_slug}", file=sys.stderr)
    es_slug = write_article(es, "es", other_slug=en_slug)
    print(f"OK ES: {es_slug}", file=sys.stderr)


if __name__ == "__main__":
    main()
