import sys,json,subprocess
for i in sys.argv[1:]:
    i=i.rstrip('/').split('/')[-1].split('?')[0]
    r=subprocess.run(['curl','-sS','--max-time','20',f'https://cdn.syndication.twimg.com/tweet-result?id={i}&token=abc'],capture_output=True).stdout
    try: d=json.loads(r)
    except Exception: print(i,'ERR',r[:100]); continue
    if not d.get('text'): print(i,'NO TEXT',str(d)[:120]); continue
    print(i,d.get('created_at','')[:10],'@'+d['user']['screen_name'],'|',d['text'].replace('\n',' / ')[:600])
