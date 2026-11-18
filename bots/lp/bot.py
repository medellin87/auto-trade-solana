# PAPER-ONLY LP forward test: Orca Whirlpool USDC/USDT (LP-V3 pair A). No wallet, no keys, no orders, no AI.
# Backtest + spec: D:\OpenBot_Work\LP-V3 (SPEC-LP-V3.md sha B3D2D442...). Real pool data from the public Orca API.
# $1000 virtual USDC -> 50/50 USDC/USDT CLMM, fixed range 0.995-1.005 USDT per USDC, never recentred.
# Fees = on-chain feeGrowthGlobal delta per unit liquidity x our virtual L (diluted by pool L), only while in range.
# Depeg guard: pool price outside 0.99-1.01 or USDC/USDT off $1 by >1% (Jupiter) -> exit all to USDC (logged);
# re-enter when price is back inside 0.995-1.005 and the guard has been clear for 6 h. Costs: $0.01 per tx, swap 0.01%.
# Benchmark: hold 1000 USDC (0%). All values are in USDC at the pool price. v1 (Narrow/Wide SOL/USDC) archived in archive/ and ../../lp/data/archive/.
import json,time,math,urllib.request,os,datetime,shutil
POOL='4fuUiYxTQ6QCrdSq9ouBYcTM7bqSwYTSyLueGZLTy4T4'  # Orca USDC/USDT, tick spacing 1, fee 0.01%
API='https://api.orca.so/v2/solana/pools/'+POOL
USDC='EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v'; USDT='Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB'
SITE=os.environ.get('LP_SITE','/workspace/paper_web/www/lp/data')
Q=2**64; VER='usdc-usdt-1'; LO,HI=0.995,1.005; G_LO,G_HI=0.99,1.01; GAS=0.01; SWAP=0.0001; CAP=1000.0; REENTER_S=6*3600
def utc(): return datetime.datetime.now(datetime.timezone.utc)
def now(): return (utc()+datetime.timedelta(hours=7)).strftime('%Y-%m-%d %H:%M:%S WIB')
def get(u):
    return json.load(urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'Mozilla/5.0'}),timeout=20))
def log(f,o): open(f,'a').write(json.dumps(o)+'\n')
def amounts(L,P):  # (usdc,usdt) for liquidity L; both tokens 6 decimals
    s,sa,sb=math.sqrt(P),math.sqrt(LO),math.sqrt(HI); s=min(max(s,sa),sb)
    return L*(1/s-1/sb)/1e6, L*(s-sa)/1e6
def lp_value(L,P): x,y=amounts(L,P); return x*P+y  # in USDT
def open_lp(usdc,P):  # swap needed share of USDC to USDT, open position; returns (L, cost in USDC)
    x,y=amounts(1e12,P); fx=x*P/(x*P+y); sw=usdc*(1-fx); c=sw*SWAP+2*GAS
    v=(usdc-c)*P; return 1e12*v/(x*P+y), c
def archive_old():  # never delete history: move incompatible/old files aside with a unique name
    os.makedirs('archive',exist_ok=True); tag=utc().strftime('%Y%m%dT%H%M%S')
    for f in ('state.json','events.jsonl','ticks.jsonl'):
        if os.path.exists(f): shutil.move(f,'archive/v1_'+tag+'_'+f)
def publish(st,row):
    os.makedirs(SITE,exist_ok=True)
    open(SITE+'/latest.json','w').write(json.dumps({'state':{k:st[k] for k in ('ver','start','P0','pool','fee_rate','tick_spacing','range','guard')},'row':row}))
    if os.path.exists('events.jsonl'): shutil.copyfile('events.jsonl',SITE+'/events.jsonl')
    open(SITE+'/ticks.jsonl','w').writelines(open('ticks.jsonl').readlines()[-120:])
st=json.load(open('state.json')) if os.path.exists('state.json') else None
if st is not None and st.get('ver')!=VER: archive_old(); st=None
while True:
    try:
        d=get(API)['data']; P=float(d['price']); fr=d['feeRate']/1e6
        fgA,fgB=int(d['feeGrowthGlobalA']),int(d['feeGrowthGlobalB']); Lact=int(d['liquidity'])
        try: j=get('https://lite-api.jup.ag/price/v3?ids='+USDC+','+USDT); uA,uB=float(j[USDC]['usdPrice']),float(j[USDT]['usdPrice'])
        except Exception: uA=uB=None
        if st is None:
            L,c=open_lp(CAP,P)
            st={'ver':VER,'start':now(),'P0':P,'pool':POOL,'fee_rate':fr,'tick_spacing':d.get('tickSpacing'),'range':[LO,HI],'guard':[G_LO,G_HI],
                'fgA':fgA,'fgB':fgB,'L':L,'usdc':0.0,'mode':'lp','fees':0.0,'cost':c,'tx':2,'exits':0,'clear_since':None,'in_range':None,'in_range_s':0.0,'run_s':0.0,'t_last':time.time()}
            log('events.jsonl',{'t':now(),'ev':'start USDC/USDT forward test','price':P,'range':[LO,HI],'cost':round(c,4),'note':'v1 Narrow/Wide SOL/USDC archived'})
        dA,dB=(fgA-st['fgA'])%(2**128),(fgB-st['fgB'])%(2**128); st['fgA'],st['fgB']=fgA,fgB
        dt=min(max(time.time()-st['t_last'],0),3*3600); st['t_last']=time.time(); st['run_s']+=dt
        bad=(not G_LO<=P<=G_HI) or (uA is not None and (abs(uA-1)>0.01 or abs(uB-1)>0.01))
        inr=st['mode']=='lp' and LO<=P<=HI
        if st['mode']=='lp':
            if inr:
                st['fees']+=st['L']*(dA/Q*P+dB/Q)/1e6*Lact/(Lact+st['L']); st['in_range_s']+=dt
            if inr!=st['in_range']: log('events.jsonl',{'t':now(),'ev':'in range' if inr else 'OUT OF RANGE (no fees)','price':P})
            if bad:
                x,y=amounts(st['L'],P); c=GAS+(y/P*SWAP+GAS if y>0 else 0); st['usdc']=x+y/P-c; st['cost']+=c; st['tx']+=2; st['L']=0.0
                st['mode']='usdc'; st['exits']+=1; st['clear_since']=None; inr=False
                log('events.jsonl',{'t':now(),'ev':'DEPEG GUARD exit -> USDC','price':P,'usdc_usd':uA,'usdt_usd':uB,'cost':round(c,4)})
        else:
            st['clear_since']=None if bad else (st['clear_since'] or time.time())
            if st['clear_since'] and time.time()-st['clear_since']>=REENTER_S and LO<=P<=HI:
                L,c=open_lp(st['usdc'],P); st['L'],st['usdc'],st['mode']=L,0.0,'lp'; st['cost']+=c; st['tx']+=2; inr=True
                log('events.jsonl',{'t':now(),'ev':'re-enter LP','price':P,'cost':round(c,4)})
        st['in_range']=inr
        # all values in USDC at the pool price (benchmark = hold 1000 USDC); Jupiter USD prices only feed the guard
        if st['mode']=='lp': x,y=amounts(st['L'],P); v=x+y/P
        else: x,y=st['usdc'],0.0; v=x
        fees=st['fees']/P; net=v+fees-CAP; days=st['run_s']/86400; hold=CAP
        row={'t':now(),'price':round(P,6),'usdc_usd':uA,'usdt_usd':uB,'fee_rate':fr,'active_L':Lact,'tvl':round(float(d['tvlUsdc'])),
             'vol24h':round(float((d.get('stats') or {}).get('24h',{}).get('volume') or 0)),'mode':st['mode'],'in_range':inr,'guard_bad':bad,
             'usdc':round(x,4),'usdt':round(y,4),'value':round(v,4),'fees':round(fees,6),'cost':round(st['cost'],4),'tx':st['tx'],'exits':st['exits'],
             'in_range_pct':round(st['in_range_s']/st['run_s'],4) if st['run_s'] else None,'days':round(days,4),
             'net_pnl':round(net,4),'apr':round(net/CAP*365/days,4) if days>=1 else None,'hold_usdc':round(hold,4),'vs_hold':round(v+fees-hold,4)}
        log('ticks.jsonl',row); json.dump(st,open('state.json','w')); publish(st,row)
    except Exception as e: print(now(),'err',repr(e),flush=True)
    if os.environ.get('LP_ONCE'): break
    time.sleep(60)