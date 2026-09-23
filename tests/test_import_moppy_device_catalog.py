import json,subprocess,sys
from pathlib import Path
SCRIPT="scripts/import-moppy-device-catalog.py"
def run(tmp_path,payload):
 p=tmp_path/"in.json"; o=tmp_path/"out.json"; p.write_text(json.dumps(payload),encoding="utf-8")
 return subprocess.run([sys.executable,SCRIPT,str(p),str(o)],capture_output=True,text=True),o
def test_accepts_large_unique_id_catalog(tmp_path):
 r,o=run(tmp_path,{"siteIds":[str(160000+i) for i in range(231)]}); assert r.returncode==0
 d=json.loads(o.read_text()); assert d["count"]==231 and d["candidateOnly"] is True and d["catalogCompleteClaim"] is False
def test_rejects_five_row_false_success(tmp_path):
 r,o=run(tmp_path,{"siteIds":["1","2","3","4","5"]}); assert r.returncode!=0 and not o.exists()
def test_accepts_only_official_detail_urls(tmp_path):
 good=[f"https://pc.moppy.jp/ad/detail.php?site_id={160000+i}" for i in range(100)]
 bad=["https://evil.example/ad/detail.php?site_id=999999","javascript:alert(1)"]
 r,o=run(tmp_path,{"siteIds":good+bad}); assert r.returncode==0
 d=json.loads(o.read_text()); assert d["count"]==100 and "999999" not in d["siteIds"]
