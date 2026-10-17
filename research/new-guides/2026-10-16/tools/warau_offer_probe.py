#!/usr/bin/env python3
"""Parse a Warau offer detail page (public HTML) into a structured dict. Network: 1 GET."""
import re,html,subprocess,sys,json
UA='Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Safari/604.1'
def fetch(pid):
    raw=subprocess.run(['curl','-sSL','--max-time','25','-A',UA,f'https://www.warau.jp/contents/point/pointEntrance.php?point_id={pid}'],capture_output=True).stdout.decode('utf-8','replace')
    return raw
def text(raw):
    t=re.sub(r'<(script|style)[\s\S]*?</\1>','',raw); t=re.sub(r'<[^>]+>','\n',t); t=html.unescape(t).replace('\xa0',' ').replace('\r','')
    t=re.sub(r'[ \t　]+',' ',t); t=re.sub(r'\n\s*\n+','\n',t); return t
def parse(pid):
    raw=fetch(pid); t=text(raw)
    title=(re.search(r'<title>(.*?)</title>',raw,re.S) or [0,''])[1].split('｜')[0].strip()
    d={'pointId':pid,'url':f'https://www.warau.jp/contents/point/pointEntrance.php?point_id={pid}','title':html.unescape(title)}
    d['live']='達成期限は' in t or '獲得条件' in t
    m=re.search(r'本日インストールの場合、達成期限は\s*(\d{4}年\d+月\d+日)',t); d['deadlineIfInstalledToday']=m.group(1) if m else ''
    m=re.search(r'■獲得条件\s*\n(.+)',t); d['condition']=m.group(1).strip() if m else ''
    # steps table between 達成条件 and 累計
    i=t.find('達成条件\n獲得pt'); mj=re.search(r'\n累計 \n[\d,]+\npt',t[i:] if i>=0 else ''); j=(i+mj.start()) if mj else -1
    steps=[]
    if i>=0 and j>i:
        seg=t[i+len('達成条件\n獲得pt'):j].strip().split('\n')
        seg=[s.strip() for s in seg if s.strip()]
        k=0
        while k+2<len(seg)+1 and k<len(seg):
            if k+2<len(seg) and seg[k+2]=='pt': steps.append((seg[k],seg[k+1])); k+=3
            else: k+=1
    d['steps']=steps
    m=re.search(r'累計\s*\n([\d,]+)\s*\npt',t); d['totalPt']=m.group(1) if m else ''
    m=re.search(r'^(iOS|Android)\s*$',t,re.M); d['os']=m.group(1) if m else ''
    m=re.search(r'広告主：(.+)',t); d['advertiser']=m.group(1).strip() if m else ''
    # reviews
    revs=[]
    for mm in re.finditer(r'さん \((.+?)\)\n(\d{4}/\d{2}/\d{2})\n((?:.+\n){1,3}?)\(([\d.]+)\)\n([\s\S]*?)\nこのクチコミは',t):
        revs.append({'who':mm.group(1),'date':mm.group(2),'title':mm.group(3).strip().replace('\n',' '),'rating':mm.group(4),'body':re.sub(r'\s+',' ',mm.group(5)).strip()})
    d['reviews']=revs
    d['notes']=[l.strip() for l in t.split('\n') if re.search(r'(購入可能|以内のみ|禁止|サーバー|移動|引継)',l)][:8]
    return d,t
if __name__=='__main__':
    for pid in sys.argv[1:]:
        d,t=parse(pid)
        print(json.dumps({k:v for k,v in d.items() if k!='reviews'},ensure_ascii=False)[:1800])
        print('reviews:',len(d['reviews']),[ (r['date'],r['title'][:20]) for r in d['reviews'][:6]])
