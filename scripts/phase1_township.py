#!/usr/bin/env python3
"""PHASE 1: Township -> Tavily -> Gemini -> verification -> JSON.
Secrets are read only from .env / environment and are never written to output.
"""
from __future__ import annotations
import json, os, re, sys, time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "township_phase1_result.json"


def load_dotenv():
    p = ROOT / ".env"
    if not p.exists(): return
    for line in p.read_text(encoding="utf-8").splitlines():
        line=line.strip()
        if not line or line.startswith("#") or "=" not in line: continue
        k,v=line.split("=",1)
        os.environ.setdefault(k.strip(),v.strip().strip('"').strip("'"))


def post_json(url, payload, headers=None, timeout=45):
    data=json.dumps(payload).encode("utf-8")
    h={"Content-Type":"application/json", **(headers or {})}
    req=Request(url,data=data,headers=h,method="POST")
    with urlopen(req,timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def tavily_search(key):
    """Townshipそのものが本文にある結果だけを集める。

    前版は「ポイ活 + ポイントサイト」の一般記事まで大量に拾い、
    Townshipが書かれていないスニペットをGeminiへ渡していた。
    今版は公式ドメイン検索 + 完全一致寄りの検索 + raw_content取得を使う。
    """
    searches=[
        ('"Township" ポイ活 案件 還元 条件', None),
        ('"Township" ポイントサイト 還元', None),
        ('"Township" ゲーム案件', None),
        ('Township', ["moppy.jp"]),
        ('Township', ["cimcome.jp"]),
        ('Township ポイントミッション', ["mercari.com"]),
    ]
    all_results=[]
    for q, domains in searches:
        payload={
            "api_key":key,
            "query":q,
            "search_depth":"advanced",
            "max_results":8,
            "include_answer":False,
            "include_raw_content":"markdown"
        }
        if domains:
            payload["include_domains"]=domains
        res=post_json("https://api.tavily.com/search", payload, timeout=60)
        for x in res.get("results",[]):
            raw=x.get("raw_content") or ""
            content=x.get("content") or ""
            title=x.get("title") or ""
            hay=(title+"\n"+content+"\n"+raw).lower()
            # 一般的なポイントサイト記事を排除。Townshipが実際に本文にあるものだけ。
            if "township" not in hay:
                continue
            all_results.append({
                "query":q,
                "title":title,
                "url":x.get("url", ""),
                "content":content,
                "raw_content":raw[:18000],
                "score":x.get("score"),
                "source_domain":(x.get("url", "").split("/")[2] if x.get("url", "").startswith("http") else "")
            })
    # URL単位で重複除去し、Townshipに関する本文が長い結果を優先
    by_url={}
    for x in all_results:
        u=x.get("url")
        if not u: continue
        old=by_url.get(u)
        if old is None or len(x.get("raw_content", ""))+len(x.get("content", "")) > len(old.get("raw_content", ""))+len(old.get("content", "")):
            by_url[u]=x
    return sorted(by_url.values(), key=lambda x: (x.get("score") or 0), reverse=True)


def _extract_interaction_text(res):
    texts=[]
    for step in res.get("steps", []):
        if step.get("type") != "model_output":
            continue
        for item in step.get("content", []):
            if item.get("type") == "text" and item.get("text"):
                texts.append(item["text"])
    if not texts:
        raise RuntimeError("Geminiからテキスト応答を取得できませんでした。")
    return "\n".join(texts).strip()


def _parse_json_text(text):
    text=text.strip()
    if text.startswith("```"):
        text=re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
        text=re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m=re.search(r"\{.*\}", text, re.S)
        if not m:
            raise RuntimeError("Gemini応答からJSONを取り出せませんでした。")
        return json.loads(m.group(0))


def _gemini_interaction(key, model, prompt):
    url="https://generativelanguage.googleapis.com/v1beta/interactions"
    payload={"model":model,"input":prompt,"store":False}
    res=post_json(url,payload,headers={"x-goog-api-key":key},timeout=180)
    return _parse_json_text(_extract_interaction_text(res))


def gemini_verify(key, search_results):
    prompt = """あなたはPOIGAME LABの案件検証AIです。以下はTownshipという文字列が実際に含まれるページだけに絞った検索結果です。公式ポイントサイトを最優先し、比較・攻略サイトは補助根拠として扱ってください。
contentだけでなくraw_contentも確認してください。Township以外のゲームの金額を絶対に混同しないでください。現在の案件である根拠が弱い場合は publishable=false にしてください。
同じポイントサイトでも条件違いを混同しないでください。金額は円換算が明確な場合だけ整数にしてください。
必ずJSONだけを返してください。Markdownや説明文は禁止です。形式:
{
 "game":"Township",
 "offers":[{"site":"","reward":null,"condition":"","platform":"","deadline":"","url":"","evidence_urls":[],"confidence":0,"publishable":false,"reason":""}],
 "verdict":"",
 "needs_human_review":false
}
confidenceは0-100。publishable=true は、ゲーム名・サイト・金額・条件・URLが十分裏付けられる場合だけ。
人間確認は原則不要にし、自動で再取得すべき曖昧さはneeds_human_review=falseのままpublishable=falseにしてください。

検索結果:
""" + json.dumps(search_results,ensure_ascii=False)[:50000]

    configured=os.getenv("GEMINI_MODEL","").strip()
    models=[]
    for m in [configured,"gemini-3.5-flash-lite","gemini-3.6-flash","gemini-3.7-flash"]:
        if m and m not in models: models.append(m)

    errors=[]
    for model in models:
        for attempt, delay in enumerate((0, 5), start=1):
            if delay: time.sleep(delay)
            try:
                print(f"      Gemini: {model} を試行 ({attempt}/2)")
                return _gemini_interaction(key, model, prompt), model
            except HTTPError as e:
                body=""
                try: body=e.read().decode("utf-8",errors="replace")
                except Exception: pass
                errors.append(f"{model} HTTP {e.code}: {body[:220]}")
                # 429/5xx are temporary: retry. Other errors: try next model immediately.
                if e.code == 429 or 500 <= e.code <= 599:
                    continue
                break
            except (URLError, TimeoutError) as e:
                errors.append(f"{model} network: {e}")
                continue
            except Exception as e:
                errors.append(f"{model}: {e}")
                break
    raise RuntimeError("Geminiの全候補モデルで検証できませんでした。\n" + "\n".join(errors[-8:]))


def main():
    load_dotenv()
    tav=os.getenv("TAVILY_API_KEY","").strip(); gem=os.getenv("GEMINI_API_KEY","").strip()
    missing=[n for n,v in [("TAVILY_API_KEY",tav),("GEMINI_API_KEY",gem)] if not v]
    if missing:
        print("ERROR: .env に " + ", ".join(missing) + " がありません。",file=sys.stderr); return 2
    print("[1/3] TavilyでTownship案件を検索中…")
    results=tavily_search(tav)
    print(f"      {len(results)}件の検索候補を取得")
    print("[2/3] Geminiで抽出・照合中…")
    # Geminiが混雑してもCollectorの成果を失わないよう、検索候補を先に保存する。
    raw_out=ROOT / "data" / "township_tavily_candidates.json"
    raw_out.parent.mkdir(parents=True,exist_ok=True)
    raw_out.write_text(json.dumps({"runAt":datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),"results":results},ensure_ascii=False,indent=2),encoding="utf-8")
    try:
        verified, used_model=gemini_verify(gem,results)
    except Exception as e:
        fail={"phase":"PHASE1_TOWNSHIP","status":"gemini_temporarily_unavailable","runAt":datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),"searchResultCount":len(results),"collectorOutput":str(raw_out.relative_to(ROOT)),"error":str(e)}
        OUT.write_text(json.dumps(fail,ensure_ascii=False,indent=2),encoding="utf-8")
        print("[3/3] Tavily収集結果は保存済み。Geminiは今回は利用できませんでした。")
        print(f"      候補: {raw_out.relative_to(ROOT)}")
        print(f"      診断: {OUT.relative_to(ROOT)}")
        return 3
    # hard safety gate: AI confidence alone is not enough; require URL and evidence.
    for o in verified.get("offers",[]):
        hard_ok=bool(o.get("url") and o.get("evidence_urls") and o.get("reward") and o.get("condition"))
        o["auto_publish_ready"] = bool(o.get("publishable") and o.get("confidence",0)>=90 and hard_ok)
    output={
      "phase":"PHASE1_TOWNSHIP","runAt":datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
      "searchResultCount":len(results),"geminiModel":used_model,"verified":verified,
      "policy":{"autoPublish":"confidence>=90 + URL + evidence + reward + condition","medium":"自動再取得","low":"不採用"}
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding="utf-8")
    ready=sum(1 for o in verified.get("offers",[]) if o.get("auto_publish_ready"))
    print("[3/3] 完了")
    print(f"      自動掲載可能: {ready}件 / AI抽出: {len(verified.get('offers',[]))}件")
    print(f"      結果: {OUT.relative_to(ROOT)}")
    return 0

if __name__=="__main__": raise SystemExit(main())
