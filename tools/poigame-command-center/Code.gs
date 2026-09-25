const CFG={ga4PropertyId:'552686542',preferredGsc:'sc-domain:poigamelab.com',host:'poigamelab.com',tz:'Asia/Tokyo',cacheSec:300};

function doGet(){
  return HtmlService.createHtmlOutputFromFile('Index')
    .setTitle('POIGAME LAB COMMAND CENTER')
    .addMetaTag('viewport','width=device-width, initial-scale=1, viewport-fit=cover');
}

function getDashboard(rangeKey,force){
  var days=rangeKey==='28d'?28:7;
  var cache=CacheService.getUserCache(), key='cc:'+days;
  if(!force){var hit=cache.get(key); if(hit) return JSON.parse(hit);}
  var w=windows_(days), out={ok:true,generatedAt:Utilities.formatDate(new Date(),CFG.tz,'yyyy-MM-dd HH:mm:ss'),days:days,ga4:null,gsc:null,combined:null,errors:[],warnings:[]};
  try{out.ga4=ga4Bundle_(w);}catch(e){out.errors.push({source:'GA4',message:safeErr_(e)});}
  try{
    out.gsc=gscBundle_(w);
    out.gsc.source='search-console-api';
  }catch(e){
    var directErr=safeErr_(e);
    try{
      out.gsc=gscViaGa4Bundle_(w);
      out.gsc.source='ga4-search-console-link';
      out.gsc.directApiError=directErr;
      out.warnings.push({source:'Search Console',message:'Search Console APIは未接続のため、GA4に連携済みの検索指標で表示しています。検索語・検索ページ別は未取得です。'});
    }catch(fallbackErr){
      out.errors.push({source:'Search data',message:'検索データを取得できませんでした。Search Console API: '+directErr+' / GA4連携: '+safeErr_(fallbackErr)});
    }
  }
  out.combined=combine_(out.ga4,out.gsc); out.ok=!!out.ga4&&!!out.gsc;
  try{cache.put(key,JSON.stringify(out),CFG.cacheSec);}catch(e){}
  return out;
}

function diagnose(){
  var r=[];
  try{ga4_({dateRanges:[{startDate:'7daysAgo',endDate:'today'}],metrics:[{name:'activeUsers'}],limit:1});r.push({source:'GA4',ok:true,detail:'接続OK'});}catch(e){r.push({source:'GA4',ok:false,detail:safeErr_(e)});}
  try{r.push({source:'Search Console API',ok:true,detail:gscSite_()});}
  catch(e){
    try{
      ga4_({dateRanges:[{startDate:'7daysAgo',endDate:'today'}],dimensions:[{name:'landingPagePlusQueryString'}],metrics:[{name:'organicGoogleSearchClicks'},{name:'organicGoogleSearchImpressions'}],limit:10});
      r.push({source:'検索データ',ok:true,detail:'Search Console APIは未接続ですが、GA4連携経由で検索指標を取得できます'});
    }catch(f){r.push({source:'検索データ',ok:false,detail:'Search Console API: '+safeErr_(e)+' / GA4連携: '+safeErr_(f)});}
  }
  return r;
}

function ga4Bundle_(w){
  var metrics=['activeUsers','sessions','screenPageViews','engagedSessions','eventCount'];
  var cur=ga4_({dateRanges:[w.cur],metrics:metrics.map(function(n){return{name:n};}),limit:1});
  var prev=ga4_({dateRanges:[w.prev],metrics:metrics.map(function(n){return{name:n};}),limit:1});
  var pages=ga4_({dateRanges:[w.cur],dimensions:[{name:'pagePath'}],metrics:[{name:'screenPageViews'},{name:'activeUsers'},{name:'sessions'}],orderBys:[{metric:{metricName:'screenPageViews'},desc:true}],limit:100});
  var cta=[],ctaError=null;
  try{
    var cr=ga4_({dateRanges:[w.cur],dimensions:[{name:'pagePath'},{name:'customEvent:cta_location'}],metrics:[{name:'eventCount'}],dimensionFilter:{filter:{fieldName:'eventName',stringFilter:{matchType:'EXACT',value:'invite_click',caseSensitive:true}}},orderBys:[{metric:{metricName:'eventCount'},desc:true}],limit:200});
    cta=gaRows_(cr).map(function(x){return{path:x.d.pagePath||'/',location:x.d['customEvent:cta_location']||'(未設定)',clicks:num_(x.m.eventCount)};});
  }catch(e){ctaError=safeErr_(e);}
  return{propertyId:CFG.ga4PropertyId,current:gaSummary_(cur,metrics),previous:gaSummary_(prev,metrics),pages:gaRows_(pages).map(function(x){return{path:x.d.pagePath||'/',views:num_(x.m.screenPageViews),users:num_(x.m.activeUsers),sessions:num_(x.m.sessions)};}),cta:aggCta_(cta),ctaByPage:aggCtaPage_(cta),ctaError:ctaError};
}


function gscViaGa4Bundle_(w){
  var names=['organicGoogleSearchClicks','organicGoogleSearchImpressions','organicGoogleSearchClickThroughRate','organicGoogleSearchAveragePosition'];
  var dims=[{name:'landingPagePlusQueryString'}];
  var cur=ga4_({dateRanges:[w.cur],dimensions:dims,metrics:names.map(function(n){return{name:n};}),limit:10000});
  var prev=ga4_({dateRanges:[w.prev],dimensions:dims,metrics:names.map(function(n){return{name:n};}),limit:10000});
  return{
    siteUrl:'GA4 linked Search Console',
    latestDate:null,
    current:gaSearchSummary_(cur),
    previous:gaSearchSummary_(prev),
    queries:null,
    pages:gaSearchPages_(cur),
    limited:true
  };
}

function gaSearchSummary_(r){
  var rows=gaRows_(r), clicks=0, impressions=0, weightedPosition=0, positionWeight=0;
  rows.forEach(function(x){
    var c=nullableNum_(x.m.organicGoogleSearchClicks), i=nullableNum_(x.m.organicGoogleSearchImpressions), p=nullableNum_(x.m.organicGoogleSearchAveragePosition);
    if(c!==null) clicks+=c;
    if(i!==null){
      impressions+=i;
      if(p!==null){weightedPosition+=p*i;positionWeight+=i;}
    }
  });
  return{
    clicks:clicks,
    impressions:impressions,
    ctr:impressions>0?clicks/impressions:null,
    position:positionWeight>0?weightedPosition/positionWeight:null
  };
}

function gaSearchPages_(r){
  return gaRows_(r).map(function(x){
    var path=x.d.landingPagePlusQueryString||'/';
    return{
      url:path,
      path:npath_(path),
      clicks:nullableNum_(x.m.organicGoogleSearchClicks),
      impressions:nullableNum_(x.m.organicGoogleSearchImpressions),
      ctr:nullableNum_(x.m.organicGoogleSearchClickThroughRate),
      position:nullableNum_(x.m.organicGoogleSearchAveragePosition)
    };
  }).filter(function(x){
    return (x.clicks||0)>0||(x.impressions||0)>0;
  });
}

function gscBundle_(w){
  var site=gscSite_();
  var cur=gsc_(site,{startDate:w.cur.startDate,endDate:w.cur.endDate,dataState:'all',rowLimit:1});
  var prev=gsc_(site,{startDate:w.prev.startDate,endDate:w.prev.endDate,dataState:'all',rowLimit:1});
  var q=gsc_(site,{startDate:w.cur.startDate,endDate:w.cur.endDate,dimensions:['query'],dataState:'all',rowLimit:250});
  var qp=gsc_(site,{startDate:w.prev.startDate,endDate:w.prev.endDate,dimensions:['query'],dataState:'all',rowLimit:250});
  var p=gsc_(site,{startDate:w.cur.startDate,endDate:w.cur.endDate,dimensions:['page'],dataState:'all',rowLimit:250});
  var d=gsc_(site,{startDate:day_(14),endDate:day_(0),dimensions:['date'],dataState:'all',rowLimit:100});
  return{siteUrl:site,latestDate:maxKey_(d.rows||[]),current:gscSummary_(cur),previous:gscSummary_(prev),queries:mergeQueries_(q.rows||[],qp.rows||[]),pages:(p.rows||[]).map(function(x){var u=x.keys&&x.keys[0]||'';return{url:u,path:path_(u),clicks:num_(x.clicks),impressions:num_(x.impressions),ctr:num_(x.ctr),position:num_(x.position)};})};
}

function combine_(ga,gsc){
  var opp=[],pages=[],gaMap={},ctaMap={};
  (ga&&ga.pages||[]).forEach(function(x){gaMap[npath_(x.path)]=x;});
  (ga&&ga.ctaByPage||[]).forEach(function(x){ctaMap[npath_(x.path)]=x;});
  (gsc&&gsc.queries||[]).forEach(function(x){
    if(x.impressions>=20&&x.position>=3&&x.position<=10&&x.ctr<0.03) opp.push({type:'ctr',score:x.impressions*Math.max(1,12-x.position),title:'CTR改善候補',label:x.query,detail:Math.round(x.impressions)+'表示 / '+Math.round(x.clicks)+'クリック / CTR '+pct_(x.ctr)+' / 順位 '+x.position.toFixed(1)});
    else if(x.impressions>=20&&x.position>10&&x.position<=20) opp.push({type:'content',score:x.impressions/Math.max(1,x.position),title:'追記・強化候補',label:x.query,detail:Math.round(x.impressions)+'表示 / 順位 '+x.position.toFixed(1)});
    if(x.prevClicks>0&&x.clicks>=x.prevClicks*1.5&&x.clicks-x.prevClicks>=3) opp.push({type:'growth',score:x.clicks-x.prevClicks,title:'伸びている検索',label:x.query,detail:Math.round(x.prevClicks)+' → '+Math.round(x.clicks)+'クリック'});
  });
  (gsc&&gsc.pages||[]).forEach(function(x){
    var k=npath_(x.path), g=gaMap[k]||{views:0,users:0,sessions:0}, c=ctaMap[k]||{clicks:0};
    pages.push({path:k,searchClicks:x.clicks,impressions:x.impressions,ctr:x.ctr,position:x.position,views:g.views,users:g.users,ctaClicks:c.clicks});
    if(x.clicks>=3&&g.users>=5&&c.clicks===0) opp.push({type:'cta',score:x.clicks+g.users/5,title:'CTA確認候補',label:k,detail:'検索 '+Math.round(x.clicks)+'クリック / GA4 '+Math.round(g.users)+'ユーザー / CTA 0'});
  });
  opp.sort(function(a,b){return b.score-a.score;}); pages.sort(function(a,b){return b.searchClicks-a.searchClicks||b.views-a.views;});
  return{opportunities:dedupe_(opp).slice(0,12),pages:pages.slice(0,40)};
}

function ga4_(body){return AnalyticsData.Properties.runReport(body,'properties/'+CFG.ga4PropertyId);}
function gsc_(site,body){
  var res=UrlFetchApp.fetch('https://www.googleapis.com/webmasters/v3/sites/'+encodeURIComponent(site)+'/searchAnalytics/query',{method:'post',contentType:'application/json',headers:{Authorization:'Bearer '+ScriptApp.getOAuthToken()},payload:JSON.stringify(body),muteHttpExceptions:true});
  return parse_(res,'Search Console');
}
function gscSite_(){
  var p=PropertiesService.getScriptProperties(), saved=p.getProperty('POIGAME_GSC_SITE'); if(saved) return saved;
  var res=UrlFetchApp.fetch('https://www.googleapis.com/webmasters/v3/sites',{headers:{Authorization:'Bearer '+ScriptApp.getOAuthToken()},muteHttpExceptions:true}), data=parse_(res,'Search Console sites'), list=data.siteEntry||[];
  var hit=list.find(function(x){return x.siteUrl===CFG.preferredGsc;})||list.find(function(x){return String(x.siteUrl||'').indexOf(CFG.host)>=0;});
  if(!hit) throw new Error('poigamelab.com のSearch Consoleプロパティが見つかりません。');
  p.setProperty('POIGAME_GSC_SITE',hit.siteUrl); return hit.siteUrl;
}
function parse_(res,label){var code=res.getResponseCode(),t=res.getContentText(),j={};try{j=t?JSON.parse(t):{};}catch(e){} if(code<200||code>=300) throw new Error(label+': '+(j.error&&j.error.message||('HTTP '+code))); return j;}
function gaRows_(r){var dh=(r.dimensionHeaders||[]).map(function(x){return x.name;}),mh=(r.metricHeaders||[]).map(function(x){return x.name;});return(r.rows||[]).map(function(row){var d={},m={};dh.forEach(function(n,i){d[n]=row.dimensionValues&&row.dimensionValues[i]?row.dimensionValues[i].value:'';});mh.forEach(function(n,i){m[n]=row.metricValues&&row.metricValues[i]?row.metricValues[i].value:'0';});return{d:d,m:m};});}
function gaSummary_(r,names){var row=gaRows_(r)[0]||{m:{}},o={};names.forEach(function(n){o[n]=num_(row.m[n]);});return o;}
function gscSummary_(r){var x=r&&r.rows&&r.rows[0]||{};return{clicks:num_(x.clicks),impressions:num_(x.impressions),ctr:num_(x.ctr),position:num_(x.position)};}
function mergeQueries_(a,b){var pm={};b.forEach(function(x){pm[x.keys&&x.keys[0]||'']=x;});return a.map(function(x){var q=x.keys&&x.keys[0]||'',p=pm[q]||{};return{query:q,clicks:num_(x.clicks),impressions:num_(x.impressions),ctr:num_(x.ctr),position:num_(x.position),prevClicks:num_(p.clicks),prevImpressions:num_(p.impressions)};});}
function aggCta_(rows){var m={};rows.forEach(function(x){m[x.location]=(m[x.location]||0)+x.clicks;});return Object.keys(m).map(function(k){return{location:k,clicks:m[k]};}).sort(function(a,b){return b.clicks-a.clicks;});}
function aggCtaPage_(rows){var m={};rows.forEach(function(x){var k=npath_(x.path);m[k]=(m[k]||0)+x.clicks;});return Object.keys(m).map(function(k){return{path:k,clicks:m[k]};});}
function windows_(days){return{cur:{startDate:day_(days-1),endDate:day_(0)},prev:{startDate:day_(days*2-1),endDate:day_(days)}};}
function day_(n){return Utilities.formatDate(new Date(Date.now()-n*86400000),CFG.tz,'yyyy-MM-dd');}
function maxKey_(rows){return rows.reduce(function(m,x){var v=x.keys&&x.keys[0]||'';return v>m?v:m;},'');}
function path_(u){return String(u||'').replace(/^https?:\/\/[^/]+/i,'')||'/';}
function npath_(p){p=String(p||'/').split('?')[0].split('#')[0];return p==='/'?'/':('/'+p.replace(/^\/+/,''));}
function num_(v){var n=Number(v||0);return isFinite(n)?n:0;}
function nullableNum_(v){if(v===undefined||v===null||v==='')return null;var n=Number(v);return isFinite(n)?n:null;}
function pct_(v){return(num_(v)*100).toFixed(1)+'%';}
function safeErr_(e){return String(e&&e.message||e||'Unknown error').replace(/Bearer\s+[A-Za-z0-9._~+\/-]+/gi,'Bearer [redacted]').slice(0,400);}
function dedupe_(rows){var s={};return rows.filter(function(x){var k=x.type+':'+x.label;if(s[k])return false;s[k]=1;return true;});}
