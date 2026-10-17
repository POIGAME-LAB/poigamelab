#!/usr/bin/env python3
"""Fetch every page of Warau reviews for one point_id (sort=new). Network: 1 GET per page (<=40). Saves JSON."""
import re,sys,json,time,html,subprocess
UA='Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Safari/604.1'
def get(pid,page):
    u=f'https://www.warau.jp/contents/point/pointEntrance.php?point_id={pid}&page={page}&sort=new'
    return subprocess.run(['curl','-sSL','--max-time','25','-A',UA,u],capture_output=True).stdout.decode('utf-8','replace')
def text(raw):
    t=re.sub(r'<(script|style)[\s\S]*?</\1>','',raw); t=re.sub(r'<[^>]+>','\n',t); t=html.unescape(t).replace('\xa0',' ').replace('\r','')
    t=re.sub(r'[ \t　]+',' ',t); return re.sub(r'\n\s*\n+','\n',t)
def reviews(t):
    out=[]
    for mm in re.finditer(r'さん \((.+?)\)\n(\d{4}/\d{2}/\d{2})\n((?:.+\n){1,3}?)\(([\d.]+)\)\n([\s\S]*?)\nこのクチコミは',t):
        out.append({'who':mm.group(1),'date':mm.group(2),'title':mm.group(3).strip().replace('\n',' '),'rating':mm.group(4),'body':re.sub(r'\s+',' ',mm.group(5)).strip()})
    return out
if __name__=='__main__':
    pid=sys.argv[1]; maxp=int(sys.argv[2]) if len(sys.argv)>2 else 40
    allr=[]; seen=set()
    for p in range(1,maxp+1):
        raw=get(pid,p); rs=reviews(text(raw))
        new=[r for r in rs if (r['date'],r['who'],r['title'],r['body'][:40]) not in seen]
        for r in new: seen.add((r['date'],r['who'],r['title'],r['body'][:40])); r['page']=p
        print(pid,'page',p,len(rs),'new',len(new),file=sys.stderr)
        if not new: break
        allr+=new; time.sleep(0.4)
    json.dump(allr,open(sys.argv[3] if len(sys.argv)>3 else f'/tmp/warau_all_{pid}.json','w'),ensure_ascii=False,indent=0)
    print(pid,'total',len(allr))
