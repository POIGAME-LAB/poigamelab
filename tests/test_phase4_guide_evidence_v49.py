import importlib.util
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("guide", ROOT/"scripts"/"collect_guide_evidence.py")
guide=importlib.util.module_from_spec(spec); spec.loader.exec_module(guide)

CFG={
 "maxSearchesPerGame":3,"maxResultsPerSearch":6,"maxDirectFetchesPerGame":8,
 "queryTemplates":["\"{game}\" 攻略","\"{game}\" 達成 日数","\"{game}\" 条件"],
 "blockedDomains":["moppy.jp"],"officialDomainsByGame":{"Game A":["official.example"]}
}
TARGET={"game":"Game A","aliases":["Game A","ゲームA"]}

def fetch_map(mapping, calls):
 def f(url):
  calls.append(url)
  v=mapping[url]
  if isinstance(v,Exception): raise v
  return v,{"httpStatus":200}
 return f

def test_search_snippet_is_never_evidence_when_page_lacks_target():
 def search(q,key,n): return {"results":[{"url":"https://guide.example/a","title":"Game A 攻略","content":"Game A 最短"}]}
 rows,diag=guide.collect_game(TARGET,CFG,"k",searcher=search,fetcher=lambda u:("<html>別ゲーム攻略</html>",{"httpStatus":200}))
 assert rows == [] and diag["confirmed"] == 0

def test_direct_target_confirmation_and_source_classification():
 urls=["https://official.example/help?a=1&utm_source=x","https://blog.example/post"]
 def search(q,key,n): return {"results":[{"url":u} for u in urls]}
 calls=[]; fetch=fetch_map({
  "https://official.example/help?a=1":"<h1>Game A 公式ヘルプ</h1>",
  "https://blog.example/post":"<p>ゲームA 攻略メモ</p>"},calls)
 rows,diag=guide.collect_game(TARGET,CFG,"k",searcher=search,fetcher=fetch)
 assert len(rows)==2 and {x["sourceType"] for x in rows}=={"official","community_guide"}
 assert all(x["status"]=="quarantined" and x["targetConfirmed"] for x in rows)
 assert rows[0]["contentHash"].startswith("sha256:")

def test_point_site_domains_are_excluded():
 def search(q,key,n): return {"results":[{"url":"https://pc.moppy.jp/something"}]}
 rows,diag=guide.collect_game(TARGET,CFG,"k",searcher=search,fetcher=lambda u:(_ for _ in ()).throw(AssertionError("must not fetch")))
 assert rows==[] and diag["directFetches"]==0

def test_tracking_variants_are_deduped_before_fetch():
 def search(q,key,n): return {"results":[{"url":"https://blog.example/p?utm_source=a"},{"url":"https://blog.example/p?utm_source=b"}]}
 calls=[]
 rows,diag=guide.collect_game(TARGET,CFG,"k",searcher=search,fetcher=fetch_map({"https://blog.example/p":"Game A guide"},calls))
 assert len(calls)==1 and len(rows)==1

def test_fetch_failure_is_not_confirmed():
 def search(q,key,n): return {"results":[{"url":"https://blog.example/p"}]}
 rows,diag=guide.collect_game(TARGET,CFG,"k",searcher=search,fetcher=lambda u:(_ for _ in ()).throw(RuntimeError("403")))
 assert rows==[] and diag["fetchErrors"]==1

def test_search_failure_does_not_create_evidence():
 def search(q,key,n): raise RuntimeError("temporary search failure")
 rows,diag=guide.collect_game(TARGET,CFG,"k",searcher=search,fetcher=lambda u:("Game A",{"httpStatus":200}))
 assert rows==[] and len(diag["searchErrors"])==3

def test_fetch_cap_bounds_network_calls():
 def search(q,key,n): return {"results":[{"url":f"https://blog.example/{i}"} for i in range(20)]}
 calls=[]
 def fetch(u): calls.append(u); return "Game A",{"httpStatus":200}
 cfg=dict(CFG,maxDirectFetchesPerGame=3)
 rows,diag=guide.collect_game(TARGET,cfg,"k",searcher=search,fetcher=fetch)
 assert len(calls)==3 and len(rows)==3

def test_run_is_quarantine_only_and_dedupes():
 def search(q,key,n): return {"results":[{"url":"https://blog.example/p"}]}
 result=guide.run(CFG,{"games":[TARGET]},"k",searcher=search,fetcher=lambda u:("Game A",{"httpStatus":200}))
 assert result["phase"]=="PHASE4_GUIDE_EVIDENCE_V49"
 assert result["publicationWrites"]==0 and len(result["evidence"])==1

def test_missing_key_fails_closed():
 try: guide.run(CFG,{"games":[TARGET]},"",searcher=lambda *a: {})
 except RuntimeError as e: assert "TAVILY_API_KEY" in str(e)
 else: raise AssertionError("missing key must fail")

def test_safe_error_redacts_secret_like_values():
 s=guide.safe_error(RuntimeError("api_key=SECRET token:ABC authorization=XYZ"))
 assert "SECRET" not in s and "ABC" not in s and "XYZ" not in s

def test_private_and_local_urls_are_never_fetched():
 for url in ["http://127.0.0.1/a","http://10.0.0.8/a","http://localhost/a","file:///etc/passwd"]:
  assert not guide.public_http_url(url)
 assert guide.public_http_url("https://guide.example/a")
