#!/usr/bin/env python3
"""Validate a residential-device supplied Moppy app-catalog identity list.

The device sends only public Moppy detail identities, never HTML. This importer is
fail-closed: an incomplete/invalid payload is rejected and cannot replace last-good.
"""
import json,re,sys
from pathlib import Path
from urllib.parse import urlparse,parse_qs
MIN_IDS=100
MAX_IDS=1000
def normalize(v):
    s=str(v or "").strip()
    if s.isdigit(): return s
    p=urlparse(s)
    if p.scheme=="https" and p.hostname=="pc.moppy.jp" and p.path=="/ad/detail.php":
        q=parse_qs(p.query); x=(q.get("site_id") or [""])[0]
        if x.isdigit(): return x
    return ""
def main(inp,out):
    data=json.loads(Path(inp).read_text(encoding="utf-8"))
    raw=data.get("siteIds") if isinstance(data,dict) else data
    if not isinstance(raw,list): raise SystemExit("siteIds must be a list")
    ids=[]; seen=set()
    for x in raw:
        n=normalize(x)
        if n and n not in seen: seen.add(n); ids.append(n)
    if len(ids)<MIN_IDS: raise SystemExit(f"refusing incomplete Moppy catalog: {len(ids)} < {MIN_IDS}")
    if len(ids)>MAX_IDS: raise SystemExit("refusing implausibly large Moppy catalog")
    result={"schemaVersion":1,"source":"moppy","scope":"public_app_catalog","candidateOnly":True,
      "catalogCompleteClaim":False,"siteIds":ids,"count":len(ids)}
    Path(out).parent.mkdir(parents=True,exist_ok=True)
    Path(out).write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"accepted":True,"count":len(ids)}))
if __name__=="__main__": main(sys.argv[1],sys.argv[2])
