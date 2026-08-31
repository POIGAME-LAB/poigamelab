#!/usr/bin/env python3
"""PHASE 3: discover trending/new point-reward games as review candidates only.

Safety invariant: this script never edits games.csv, offers.csv, or published_offers.csv.
Direct first-party HTTP is preferred for stable official listing pages. Firecrawl is only a
best-effort fallback for sources that cannot be read directly. Gemini only extracts game-name
candidates; Python normalizes, deduplicates, scores, computes evidence confidence, and writes a review queue.
"""
from __future__ import annotations
import csv, json, os, re, sys, unicodedata
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CONFIG = ROOT / "config" / "trend_discovery.json"
NOW = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
DIRECT_TIMEOUT_SECONDS = 15
DIRECT_MAX_BYTES = 900_000
DEFAULT_EXTRACTION_CHUNK_CHARS = 4500
DEFAULT_EXTRACTION_CHUNK_OVERLAP = 300
DEFAULT_MAX_CHUNKS_PER_RESULT = 6
DEFAULT_MAX_EXTRACTION_BATCH_CHARS = 18_000
DEFAULT_MAX_EXTRACTION_BATCHES = 6

sys.path.insert(0, str(ROOT / "scripts"))
from firecrawl_township_probe import firecrawl_post, gemini_call  # noqa: E402


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def known_games():
    with (ROOT / "games.csv").open(encoding="utf-8", newline="") as f:
        return [r.get("name", "").strip() for r in csv.DictReader(f) if r.get("name", "").strip()]


def safe_url(url):
    try:
        u = urlparse(url or "")
        if u.scheme not in {"http", "https"} or not u.netloc:
            return ""
        return urlunparse((u.scheme.lower(), u.netloc.lower(), u.path, "", "", ""))
    except Exception:
        return ""


DIRECT_SELECTOR_PARAMS = {
    "_category_id", "category_group", "category_id", "display_style", "page", "point_group", "sort"
}

def safe_direct_url(url):
    """Keep only stable public listing selectors so multiple configured pages remain distinct."""
    try:
        u = urlparse(url or "")
        if u.scheme not in {"http", "https"} or not u.netloc:
            return ""
        pairs=[]
        for key, value in parse_qsl(u.query, keep_blank_values=False):
            if key in DIRECT_SELECTOR_PARAMS:
                pairs.append((key, value))
        query=urlencode(pairs)
        return urlunparse((u.scheme.lower(), u.netloc.lower(), u.path, "", query, ""))
    except Exception:
        return ""


def _host_allowed(url, domains):
    host = (urlparse(url or "").hostname or "").lower().rstrip(".")
    for domain in domains or []:
        d = str(domain).lower().strip().lstrip(".").rstrip(".")
        if d and (host == d or host.endswith("." + d)):
            return True
    return False


def normalize_name(name):
    s = unicodedata.normalize("NFKC", str(name or ""))
    s = re.sub(r"\s+", " ", s.strip())
    for left, right in (("『", "』"), ("「", "」"), ("【", "】"), ("[", "]")):
        if s.startswith(left) and s.endswith(right) and len(s) > 2:
            s = s[1:-1].strip()
            break
    return s[:100]


_PROVIDER_PREFIX_RE = re.compile(r"^【(?:SKYFLAG|GFRewards|Zucks|SmaAD|myChips|TyrAds|Ayet)】\s*", re.I)
_PLATFORM_PREFIX_RE = re.compile(r"^(?:Android|iOS)[_\s]+", re.I)
_STEPUP_SUFFIX_RE = re.compile(r"\s*(?:\(\s*(?:Step\s*Up|ステップアップ)\s*\)|<\s*(?:Step\s*Up|ステップアップ)\s*>|【\s*(?:Step\s*Up|ステップアップ)\s*】)\s*$", re.I)

def canonical_game_name(name):
    """Conservative deterministic identity cleanup for campaign decorations only."""
    s=normalize_name(name)
    s=_PLATFORM_PREFIX_RE.sub("", s)
    s=_PROVIDER_PREFIX_RE.sub("", s)
    s=_STEPUP_SUFFIX_RE.sub("", s).strip()
    return s[:100]


def game_identity_key(name):
    return canonical_game_name(name).casefold()


class _HTMLTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.title_parts = []
        self._skip_depth = 0
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip_depth += 1
        if tag == "title":
            self._in_title = True
        if tag in {"p", "br", "li", "div", "section", "article", "h1", "h2", "h3", "tr"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "svg"} and self._skip_depth:
            self._skip_depth -= 1
        if tag == "title":
            self._in_title = False
        if tag in {"p", "li", "div", "section", "article", "h1", "h2", "h3", "tr"}:
            self.parts.append("\n")

    def handle_data(self, data):
        if self._skip_depth:
            return
        text = re.sub(r"\s+", " ", data or " ").strip()
        if not text:
            return
        self.parts.append(text)
        self.parts.append(" ")
        if self._in_title:
            self.title_parts.append(text)

    def result(self):
        raw = "".join(self.parts)
        raw = re.sub(r"[ \t]+", " ", raw)
        raw = re.sub(r"\n\s*\n+", "\n", raw)
        return " ".join(self.title_parts).strip(), raw.strip()


def direct_fetch_seed(item, url, timeout=DIRECT_TIMEOUT_SECONDS, max_bytes=DIRECT_MAX_BYTES):
    safe = safe_direct_url(url)
    if not safe:
        raise ValueError("invalid direct URL")
    if not _host_allowed(url, item.get("includeDomains") or []):
        raise ValueError("direct URL domain is not registered for source")
    req = Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; POIGAME-LAB/1.0; +https://poigamelab.com/)",
        "Accept": "text/html,application/xhtml+xml;q=0.9,text/plain;q=0.8,*/*;q=0.1",
        "Accept-Language": "ja,en-US;q=0.7,en;q=0.5",
        "Cache-Control": "no-cache",
    })
    with urlopen(req, timeout=timeout) as response:  # nosec B310: URL is config allowlisted above
        content_type = (response.headers.get("Content-Type") or "").lower()
        if content_type and not any(x in content_type for x in ("text/html", "application/xhtml+xml", "text/plain")):
            raise ValueError("direct response is not text/html")
        body = response.read(max_bytes + 1)
        if len(body) > max_bytes:
            body = body[:max_bytes]
        charset = response.headers.get_content_charset() or "utf-8"
    html = body.decode(charset, errors="replace")
    parser = _HTMLTextExtractor()
    parser.feed(html)
    title, text = parser.result()
    if len(text) < 40:
        raise ValueError("direct response did not contain enough readable text")
    return {
        "sourceId": item["id"], "sourceType": item.get("sourceType", "web"),
        "title": title, "description": "", "url": safe, "text": text,
        "retrieval": "direct_http",
    }


def firecrawl_scrape_seed(fc_key, item, url):
    payload = {
        "url": url, "formats": ["markdown"], "onlyMainContent": True,
        "mobile": True, "waitFor": 1500, "timeout": 60000,
        "location": {"country":"JP", "languages":["ja-JP","ja"]},
        "blockAds": True, "maxAge": 1800000,
    }
    res = firecrawl_post(fc_key, "scrape", payload, attempts=2)
    data = res.get("data") or {}
    safe = safe_url(url)
    if not safe or not isinstance(data, dict):
        return None
    return {
        "sourceId": item["id"], "sourceType": item.get("sourceType", "web"),
        "title": (data.get("metadata") or {}).get("title") or "",
        "description": (data.get("metadata") or {}).get("description") or "",
        "url": safe, "text": data.get("markdown") or "", "retrieval": "firecrawl_scrape",
    }


def firecrawl_search(fc_key, item, limit):
    payload = {
        "query": item["query"], "limit": limit, "sources": ["web"],
        "includeDomains": item.get("includeDomains") or [],
        "location": "Japan", "country": "JP", "timeout": 60000,
        "scrapeOptions": {"formats": ["markdown"], "onlyMainContent": True,
                          "location": {"country":"JP", "languages":["ja-JP","ja"]},
                          "blockAds": True, "maxAge": 1800000},
    }
    res = firecrawl_post(fc_key, "search", payload, attempts=2)
    data = res.get("data") or {}
    return data.get("web", []) if isinstance(data, dict) else []


def _chunk_text(text, chunk_chars=DEFAULT_EXTRACTION_CHUNK_CHARS, overlap=DEFAULT_EXTRACTION_CHUNK_OVERLAP, max_chunks=DEFAULT_MAX_CHUNKS_PER_RESULT):
    """Split long listing text on readable boundaries without silently discarding the tail."""
    text = str(text or "").strip()
    if not text:
        return []
    chunk_chars = max(1000, int(chunk_chars or DEFAULT_EXTRACTION_CHUNK_CHARS))
    overlap = max(0, min(int(overlap or 0), chunk_chars // 3))
    max_chunks = max(1, int(max_chunks or DEFAULT_MAX_CHUNKS_PER_RESULT))
    if len(text) <= chunk_chars:
        return [text]
    chunks=[]; start=0
    while start < len(text) and len(chunks) < max_chunks:
        target=min(len(text), start + chunk_chars)
        end=target
        if target < len(text):
            floor=start + max(1, chunk_chars // 2)
            candidates=[text.rfind("\n", floor, target), text.rfind("。", floor, target), text.rfind(" ", floor, target)]
            boundary=max(candidates)
            if boundary > start:
                end=boundary + 1
        piece=text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(text):
            break
        next_start=max(start + 1, end - overlap)
        if next_start <= start:
            next_start=end
        start=next_start
    return chunks


def prepare_extraction_items(items, cfg=None):
    """Create bounded extraction units while preserving parent source/url identity."""
    cfg=cfg or {}
    chunk_chars=int(cfg.get("extractionChunkChars", DEFAULT_EXTRACTION_CHUNK_CHARS))
    overlap=int(cfg.get("extractionChunkOverlap", DEFAULT_EXTRACTION_CHUNK_OVERLAP))
    max_chunks=int(cfg.get("maxChunksPerResult", DEFAULT_MAX_CHUNKS_PER_RESULT))
    units=[]
    for parent_index, x in enumerate(items):
        chunks=_chunk_text(x.get("text", ""), chunk_chars, overlap, max_chunks)
        for chunk_index, text in enumerate(chunks):
            row=dict(x)
            row["text"]=text
            row["parentIndex"]=parent_index
            row["chunkIndex"]=chunk_index
            row["chunkCount"]=len(chunks)
            row["extractionBatchChars"]=int(cfg.get("maxExtractionBatchChars", DEFAULT_MAX_EXTRACTION_BATCH_CHARS))
            row["extractionBatchLimit"]=int(cfg.get("maxExtractionBatches", DEFAULT_MAX_EXTRACTION_BATCHES))
            units.append(row)
    return units


def _extraction_batches(items, max_chars=DEFAULT_MAX_EXTRACTION_BATCH_CHARS, max_batches=DEFAULT_MAX_EXTRACTION_BATCHES):
    max_chars=max(4000, int(max_chars or DEFAULT_MAX_EXTRACTION_BATCH_CHARS))
    max_batches=max(1, int(max_batches or DEFAULT_MAX_EXTRACTION_BATCHES))
    batches=[]; current=[]; size=0
    for item in items:
        estimated=len(item.get("text", "")) + len(item.get("title", "")) + len(item.get("description", "")) + 300
        if current and size + estimated > max_chars:
            batches.append(current); current=[]; size=0
            if len(batches) >= max_batches:
                break
        current.append(item); size += estimated
    if current and len(batches) < max_batches:
        batches.append(current)
    return batches


def _extract_names_batch(gemini_key, items, known):
    compact=[]
    for x in items:
        compact.append({"sourceId":x["sourceId"], "sourceType":x["sourceType"],
                        "title":x["title"][:300], "description":x["description"][:500],
                        "url":x["url"], "text":x["text"]})
    prompt = f'''あなたはPOIGAME LABの「新規ゲーム候補名抽出器」です。検索結果から、ポイ活のゲーム案件として明確に言及されるゲーム名だけを抽出してください。
既知ゲーム: {json.dumps(known, ensure_ascii=False)}
厳守:
- ポイントサイト名、一般語（ゲーム、アプリ、ポイ活等）、会社名をゲーム名にしない。
- 根拠が弱い推測名を作らない。
- 同一ゲームの表記揺れはcanonical_nameを統一する。
- known_gameは既知ゲームと同一ならtrue。
- evidence_indexesは下記resultsの0始まりindexのみ。
- JSON以外禁止。
形式: {{"games":[{{"canonical_name":"","aliases":[],"known_game":false,"evidence_indexes":[],"confidence":0}}]}}
results={json.dumps(compact, ensure_ascii=False)}'''
    out = gemini_call(gemini_key, os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite"), prompt)
    return out.get("games", []) if isinstance(out, dict) else []


def extract_names(gemini_key, items, known, cfg=None):
    """Extract from bounded batches and remap batch-local evidence indexes to global units."""
    cfg=cfg or {}
    first=items[0] if items else {}
    batch_chars=cfg.get("maxExtractionBatchChars", first.get("extractionBatchChars", DEFAULT_MAX_EXTRACTION_BATCH_CHARS))
    batch_limit=cfg.get("maxExtractionBatches", first.get("extractionBatchLimit", DEFAULT_MAX_EXTRACTION_BATCHES))
    batches=_extraction_batches(items, batch_chars, batch_limit)
    extracted=[]; offset=0
    for batch in batches:
        rows=_extract_names_batch(gemini_key, batch, known)
        for row in rows:
            clone=dict(row)
            clone["evidence_indexes"]=[offset+i for i in (row.get("evidence_indexes") or [])
                                       if isinstance(i,int) and 0 <= i < len(batch)]
            if clone["evidence_indexes"]:
                extracted.append(clone)
        offset += len(batch)
    return extracted


def score_candidates(extracted, items, known):
    known_keys={game_identity_key(x):x for x in known if game_identity_key(x)}
    merged={}
    for g in extracted:
        raw_name=normalize_name(g.get("canonical_name"))
        name=canonical_game_name(raw_name)
        if len(name) < 2: continue
        idxs=[]
        for i in g.get("evidence_indexes") or []:
            if isinstance(i,int) and 0 <= i < len(items): idxs.append(i)
        if not idxs: continue
        key=game_identity_key(name)
        if not key: continue
        row=merged.setdefault(key, {"game":name,"aliases":set(),"knownGame":False,"evidence":[],"modelConfidence":0})
        if raw_name and raw_name != name:
            row["aliases"].add(raw_name)
        row["aliases"].update(normalize_name(a) for a in (g.get("aliases") or []) if normalize_name(a))
        row["knownGame"] = bool(g.get("known_game")) or key in known_keys
        row["modelConfidence"] = max(row["modelConfidence"], max(0, min(100, int(g.get("confidence") or 0))))
        for i in idxs:
            ev=items[i]
            marker=(ev["sourceId"],ev["url"])
            if marker not in {(e["sourceId"],e["url"]) for e in row["evidence"]}: row["evidence"].append(ev)
    out=[]
    for row in merged.values():
        unique_sources=len({e["sourceId"] for e in row["evidence"]})
        unique_types=len({e["sourceType"] for e in row["evidence"]})
        mentions=len(row["evidence"])
        score=min(100, unique_sources*25 + unique_types*15 + min(mentions,5)*5)
        # Promotion confidence is evidence-derived, not Gemini self-confidence. This preserves
        # the architecture rule "Gemini reads, Python judges" and prevents a single source
        # from becoming research-ready merely because the model reports high confidence.
        evidence_confidence = 0 if unique_sources == 0 else (45 if unique_sources == 1 else min(100, 80 + (unique_sources - 2) * 10))
        # Model confidence is never allowed to elevate a single-source candidate. Once Python
        # has independently established 2+ sources, the model value may refine (not weaken)
        # the evidence floor; the independent-source gate remains authoritative.
        promotion_confidence = evidence_confidence if unique_sources < 2 else max(evidence_confidence, row["modelConfidence"])
        status="既知ゲーム" if row["knownGame"] else ("要確認" if score >= 30 else "保留")
        out.append({"game":row["game"],"aliases":sorted(row["aliases"]),"knownGame":row["knownGame"],
                    "score":score,"confidence":promotion_confidence,"modelConfidence":row["modelConfidence"],"mentionCount":mentions,
                    "sourceCount":unique_sources,"sourceTypeCount":unique_types,"status":status,
                    "evidence":[{"sourceId":e["sourceId"],"sourceType":e["sourceType"],"title":e["title"],"url":e["url"]} for e in row["evidence"]]})
    return sorted(out,key=lambda x:(x["knownGame"],-x["score"],-x["confidence"],x["game"].lower()))


def atomic_json(path, obj):
    path.parent.mkdir(parents=True,exist_ok=True); tmp=path.with_suffix(path.suffix+".tmp")
    tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"); tmp.replace(path)


def _safe_error_text(value, limit=180):
    text = re.sub(r"(?i)(bearer\s+)[A-Za-z0-9._~+\-/=]+", r"\1[REDACTED]", str(value or ""))
    text = re.sub(r"(?i)(api[_-]?key|token|authorization)(\s*[:=]\s*)[^\s,;]+", r"\1\2[REDACTED]", text)
    text = re.sub(r"[\r\n\t]+", " ", text).strip()
    return text[:limit]


def build_status(result):
    diagnostics=[]
    for raw in result.get("diagnostics") or []:
        d={
            "sourceId": raw.get("sourceId", ""),
            "ok": bool(raw.get("ok")),
            "directAttempted": bool(raw.get("directAttempted")),
            "directResults": int(raw.get("directResults") or 0),
            "firecrawlAttempted": bool(raw.get("firecrawlAttempted")),
            "searchResults": int(raw.get("results") or 0),
            "fallbackAttempted": bool(raw.get("fallbackAttempted")),
            "fallbackResults": int(raw.get("fallbackResults") or 0),
        }
        if raw.get("directErrors"):
            d["directErrors"]=[_safe_error_text(x) for x in raw.get("directErrors") if _safe_error_text(x)]
        if raw.get("searchError"):
            d["searchError"]=_safe_error_text(raw.get("searchError"))
        if raw.get("fallbackErrors"):
            d["fallbackErrors"]=[_safe_error_text(x) for x in raw.get("fallbackErrors") if _safe_error_text(x)]
        diagnostics.append(d)
    return {
        "lastRun":result["generatedAt"],
        **result["summary"],
        "ok":result["summary"]["failedSources"]==0,
        "diagnostics":diagnostics,
    }


def run(fc_key, gemini_key, config=None):
    cfg=config or load_json(CONFIG); items=[]; diagnostics=[]
    for q in cfg.get("queries",[]):
        direct_count = 0
        direct_errors = []
        direct_urls = q.get("directUrls") or []
        for direct_url in direct_urls:
            try:
                row = direct_fetch_seed(q, direct_url)
                if row and row.get("text"):
                    items.append(row); direct_count += 1
            except Exception as e:
                direct_errors.append(_safe_error_text(e))

        search_error = None
        count = 0
        firecrawl_attempted = False
        should_try_firecrawl = direct_count == 0 and q.get("firecrawlFallback", True)
        if should_try_firecrawl:
            if fc_key:
                firecrawl_attempted = True
                try:
                    raw=firecrawl_search(fc_key,q,int(cfg.get("maxResultsPerQuery",8)))
                    for x in raw:
                        url=safe_url(x.get("url") or (x.get("metadata") or {}).get("sourceURL"))
                        if not url: continue
                        items.append({"sourceId":q["id"],"sourceType":q.get("sourceType","web"),
                                      "title":x.get("title") or "","description":x.get("description") or "",
                                      "url":url,"text":x.get("markdown") or "", "retrieval":"firecrawl_search"}); count+=1
                except Exception as e:
                    search_error = _safe_error_text(e)
            else:
                search_error = "Firecrawl unavailable: API key not configured"

        recovered = 0
        fallback_errors = []
        fallback_attempted = bool(not direct_urls and direct_count == 0 and firecrawl_attempted and (search_error or count == 0) and q.get("fallbackUrls"))
        if fallback_attempted:
            for fallback_url in q.get("fallbackUrls") or []:
                try:
                    row = firecrawl_scrape_seed(fc_key, q, fallback_url)
                    if row and row.get("text"):
                        items.append(row); recovered += 1
                except Exception as e:
                    fallback_errors.append(_safe_error_text(e))

        ok = direct_count > 0 or count > 0 or recovered > 0
        diag = {"sourceId":q["id"],"ok":ok,"directAttempted":bool(direct_urls),"directResults":direct_count,
                "firecrawlAttempted":firecrawl_attempted,"results":count,
                "fallbackAttempted":fallback_attempted,"fallbackResults":recovered}
        if direct_errors: diag["directErrors"] = direct_errors
        if search_error: diag["searchError"] = search_error
        if fallback_errors: diag["fallbackErrors"] = fallback_errors
        diagnostics.append(diag)
    # exact result dedupe before Gemini
    uniq={}
    for x in items: uniq[(x["sourceId"], x["url"])]=x
    items=list(uniq.values()); known=known_games()
    extraction_items=prepare_extraction_items(items,cfg)
    extracted=extract_names(gemini_key,extraction_items,known) if extraction_items else []
    candidates=score_candidates(extracted,extraction_items,known)
    return {"schemaVersion":1,"generatedAt":NOW,"candidateOnly":True,"autoPublish":False,
            "summary":{"searchResults":len(items),"candidates":len(candidates),
                       "newReviewCandidates":sum(1 for x in candidates if x["status"]=="要確認"),
                       "failedSources":sum(1 for x in diagnostics if not x["ok"])},
            "diagnostics":diagnostics,"candidates":candidates}


def main():
    fc=os.getenv("FIRECRAWL_API_KEY","").strip(); gem=os.getenv("GEMINI_API_KEY","").strip()
    if not gem: raise SystemExit("GEMINI_API_KEY is required")
    result=run(fc,gem); atomic_json(DATA/"trend_candidates.json",result)
    atomic_json(DATA/"trend_status.json",build_status(result))
    print(json.dumps(result["summary"],ensure_ascii=False))

if __name__ == "__main__": main()
