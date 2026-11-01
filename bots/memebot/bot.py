#!/usr/bin/env python3
# PAPER ONLY. No wallet, no keys, no orders. Public data: DexScreener + RugCheck.
import json,time,os,urllib.request,datetime,csv
D=os.path.dirname(os.path.abspath(__file__))
WIB=datetime.timezone(datetime.timedelta(hours=7))
FEE=0.01; START=200.0; MAXPCT=0.10; STOP=-0.08; TRAIL_ON=0.15; TRAIL=0.10
def now(): return datetime.datetime.now(WIB).strftime('%Y-%m-%d %H:%M:%S WIB')
def get(u):
    r=urllib.request.Request(u,headers={'User-Agent':'paperbot/1.0'})
    with urllib.request.urlopen(r,timeout=20) as f: return json.load(f)
def log(fn,obj):
    with open(os.path.join(D,fn),'a') as f: f.write(json.dumps(obj)+'\n')
SF=os.path.join(D,'state.json')
st=json.load(open(SF)) if os.path.exists(SF) else {'cash':START,'pos':{},'seen':{},'trades':[]}
def save(): json.dump(st,open(SF+'.tmp','w')); os.replace(SF+'.tmp',SF)
def best_pair(mint):
    ps=[p for p in (get(f'https://api.dexscreener.com/latest/dex/tokens/{mint}').get('pairs') or []) if p.get('chainId')=='solana']
    return max(ps,key=lambda p:(p.get('liquidity') or {}).get('usd',0)) if ps else None
def rug(mint):
    try: d=get(f'https://api.rugcheck.xyz/v1/tokens/{mint}/report')
    except Exception as e: return None
    if 'error' in d: return None
    return d
def kill(mint,sym,why): log('kills.jsonl',{'t':now(),'mint':mint,'sym':sym,'reason':why})
def evaluate(mint):
    p=best_pair(mint)
    if not p: return kill(mint,'?','no solana pair')
    sym=p['baseToken']['symbol']; liq=(p.get('liquidity') or {}).get('usd',0) or 0
    v1=(p.get('volume') or {}).get('h1',0) or 0; tx=(p.get('txns') or {}).get('h1',{})
    b,s=tx.get('buys',0),tx.get('sells',0); m1=(p.get('priceChange') or {}).get('h1',0) or 0
    if v1<40000: return kill(mint,sym,f'vol1h {v1:.0f}<40k')
    if liq<20000: return kill(mint,sym,f'liq {liq:.0f}<20k')
    r=rug(mint)
    if not r: return kill(mint,sym,'rugcheck data unavailable')
    if r.get('mintAuthority'): return kill(mint,sym,'mint not revoked')
    if r.get('freezeAuthority'): return kill(mint,sym,'freeze not revoked')
    # exclude AMM pool accounts from concentration if flagged by rugcheck
    pools={m.get('liquidityA') for m in r.get('markets') or []}|{m.get('liquidityB') for m in r.get('markets') or []}
    top=sum([h.get('pct',0) for h in (r.get('topHolders') or []) if h.get('address') not in pools and h.get('owner') not in pools][:10])
    if top>25: return kill(mint,sym,f'top10 {top:.1f}%>25')
    lps=[(m.get('lp') or {}).get('lpLockedPct') for m in r.get('markets') or []]
    lps=[x for x in lps if x is not None]
    if lps and max(lps)<90: return kill(mint,sym,f'LP locked {max(lps):.0f}%<90')
    danger=[x.get('name') for x in r.get('risks') or [] if x.get('level')=='danger']
    if danger: return kill(mint,sym,'risk:'+';'.join(danger))
    bsr=b/max(b+s,1)
    sc=round(0.35*min(v1/200000,1)+0.25*min(liq/100000,1)+0.25*min(max(bsr-0.4,0)/0.3,1)+0.15*min(max(m1,0)/50,1),3)
    log('scores.jsonl',{'t':now(),'mint':mint,'sym':sym,'score':sc,'vol1h':v1,'liq':liq,'buys':b,'sells':s,'chg1h':m1,'top10':round(top,1),'lpLocked':lps,'url':p['url']})
    if sc<0.6: return kill(mint,sym,f'score {sc}<0.6')
    if mint in st['pos']: return
    eq=equity_est(); size=min(eq*MAXPCT,st['cash'])
    if size<1: return
    px=float(p['priceUsd']); imp=size/liq; fill=px*(1+FEE+imp)
    st['cash']-=size
    st['pos'][mint]={'sym':sym,'pair':p['pairAddress'],'url':p['url'],'entry':fill,'mkt_entry':px,'size':size,'qty':size/fill,'peak':px,'t':now(),'liq':liq}
    log('trades.jsonl',{'t':now(),'side':'BUY','mint':mint,'sym':sym,'pair':p['pairAddress'],'url':p['url'],'mkt_px':px,'fill_px':fill,'usd':round(size,2),'score':sc})
    save()
def equity_est(): return st['cash']+sum(v['size'] for v in st['pos'].values())
def manage():
    for mint,v in list(st['pos'].items()):
        try: p=best_pair(mint)
        except Exception: continue
        if not p: continue
        px=float(p['priceUsd']); v['peak']=max(v['peak'],px); ch=px/v['mkt_entry']-1; why=None
        if px/v['entry']-1<=STOP: why='stop -8%'
        elif v['peak']/v['mkt_entry']-1>=TRAIL_ON and px<=v['peak']*(1-TRAIL): why='trail stop'
        if why:
            liq=(p.get('liquidity') or {}).get('usd',1) or 1
            out=v['qty']*px*(1-FEE-min(v['size']/liq,0.5)); pnl=out-v['size']
            st['cash']+=out; del st['pos'][mint]
            rec={'t':now(),'side':'SELL','mint':mint,'sym':v['sym'],'pair':v['pair'],'url':v['url'],'entry_fill':v['entry'],'exit_mkt_px':px,'usd_in':round(v['size'],2),'usd_out':round(out,2),'pnl':round(pnl,2),'pct':round(pnl/v['size']*100,1),'reason':why}
            log('trades.jsonl',rec); st['trades'].append(rec)
    save()
def summary():
    T=st['trades']; w=[t for t in T if t['pnl']>0]
    s=f"Updated {now()} | PAPER ONLY\nCash ${st['cash']:.2f} | open {len(st['pos'])} (cost ${sum(v['size'] for v in st['pos'].values()):.2f}) | start ${START}\nClosed trades {len(T)} W{len(w)}/L{len(T)-len(w)}\n"
    if T: s+=f"Biggest win {max(T,key=lambda t:t['pnl'])['pnl']} | Worst {min(T,key=lambda t:t['pnl'])['pnl']}\n"
    open(os.path.join(D,'summary.txt'),'w').write(s)
while True:
    try:
        prof=get('https://api.dexscreener.com/token-profiles/latest/v1')
        try: prof+=get('https://api.dexscreener.com/token-boosts/latest/v1')
        except Exception: pass
        mints={x['tokenAddress'] for x in prof if x.get('chainId')=='solana'}
        tnow=time.time()
        for m in mints:
            if tnow-st['seen'].get(m,0)<1800 or m in st['pos']: continue
            st['seen'][m]=tnow
            try: evaluate(m)
            except Exception as e: kill(m,'?',f'err {e}')
            time.sleep(1.5)
        st['seen']={k:v for k,v in st['seen'].items() if tnow-v<86400}
        manage(); summary(); save()
        log('cycles.jsonl',{'t':now(),'candidates':len(mints),'cash':round(st['cash'],2),'open':len(st['pos'])})
    except Exception as e: log('errors.jsonl',{'t':now(),'err':str(e)})
    time.sleep(45)
