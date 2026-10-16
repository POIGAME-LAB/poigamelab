#!/usr/bin/env python3
"""fetch URL -> readable text saved in research/<slug>.txt ; print head + keyword windows."""
import sys,re,subprocess,hashlib,html,os,json
url=sys.argv[1]
kw=sys.argv[2] if len(sys.argv)>2 else r'(\d+\s*日目|\d+\s*日で|\d+\s*日間|日目|Lv\.?\s*\d+|レベル\s*\d+|達成|クリア|断念|撤退|課金)'
maxwin=int(sys.argv[3]) if len(sys.argv)>3 else 14
raw=subprocess.run(['curl','-sSL','--max-time','25','-A','Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Safari/605.1.15',url],capture_output=True).stdout
t=raw.decode('utf-8',errors='replace')
title=(re.search(r'<title[^>]*>(.*?)</title>',t,re.S) or [0,''])[1]
t=re.sub(r'<(script|style|noscript|svg|head)[\s\S]*?</\1>','',t,flags=re.I)
t=re.sub(r'<br\s*/?>|</(p|div|li|h\d|tr)>','\n',t,flags=re.I)
t=re.sub(r'<[^>]+>','',t); t=html.unescape(t)
t=re.sub(r'[ \t　]+',' ',t); t=re.sub(r'\n\s*\n+','\n',t).strip()
slug=hashlib.md5(url.encode()).hexdigest()[:10]
open(f'research/{slug}.txt','w').write(url+'\n'+title.strip()+'\n'+t)
print('URL',url,'| slug',slug,'| chars',len(t),'| title',html.unescape(title).strip()[:90])
if len(t)<400: print('!! little text'); sys.exit()
lines=t.split('\n'); shown=0
for i,l in enumerate(lines):
    if re.search(kw,l) and 8<len(l)<400:
        print('  >',l.strip()[:220]); shown+=1
        if shown>=maxwin: break
