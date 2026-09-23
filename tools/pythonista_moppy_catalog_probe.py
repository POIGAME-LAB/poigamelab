# Pythonista 3 / iPhone residential Moppy catalog probe
# Public pages only. Does not send data anywhere.
import urllib.request, urllib.parse, http.cookiejar, re, json

BOOT = "https://pc.moppy.jp/category/list.php?parent_category=4&child_category=52&af_sorter=1&page=1"
AJAX = "https://pc.moppy.jp/ajax/category/get_list.php"
UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 26_0 like Mac OS X) AppleWebKit/605.1.15 Version/26.0 Mobile/15E148 Safari/604.1"

jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

def get(url, headers=None):
    h={"User-Agent":UA,"Accept-Language":"ja-JP,ja;q=0.9"}
    if headers: h.update(headers)
    req=urllib.request.Request(url,headers=h)
    with opener.open(req,timeout=30) as r:
        return r.getcode(), r.read().decode("utf-8","replace")

status, boot = get(BOOT)
print("BOOT:",status,"bytes:",len(boot))

all_ids=[]
seen=set()
first_count=None
for page in range(1,61):
    qs=urllib.parse.urlencode({
        "parent_category":"4","child_category":"52","objective_category":"0",
        "current_page":str(page),"af_sorter":"1","exclude_purchased":"true"
    })
    status, html=get(AJAX+"?"+qs,{
        "Referer":BOOT,
        "X-Requested-With":"XMLHttpRequest",
        "Accept":"text/html, */*; q=0.01"
    })
    ids=re.findall(r'detail\.php\?site_id=(\d+)',html)
    ids=list(dict.fromkeys(ids))
    if page==1:
        first_count=len(ids)
        m=re.search(r'アプリ広告一覧\s*[（(]\s*(\d+)件',html)
        print("PAGE 1 advertised count:",m.group(1) if m else "unknown")
    print("PAGE",page,"HTTP",status,"IDs",len(ids))
    if not ids:
        break
    new=0
    for sid in ids:
        if sid not in seen:
            seen.add(sid); all_ids.append(sid); new+=1
    if new==0:
        print("Repeated page; stopping.")
        break

print("\nUNIQUE SITE IDs:",len(all_ids))
print("FIRST 20:",all_ids[:20])
if len(all_ids) < 100:
    print("\nRESULT: INCOMPLETE. Nothing will be sent.")
else:
    payload={"siteIds":all_ids}
    print("\nRESULT: CATALOG-SCALE DATA FOUND.")
    print("JSON chars:",len(json.dumps(payload,separators=(',',':'))))
