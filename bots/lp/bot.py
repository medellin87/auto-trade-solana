# PAPER-ONLY LP simulator. No wallet, no keys, no AI. Real Orca Whirlpool data.
import json,time,math,urllib.request,os,datetime
POOL='Czfq3xZZDmsdGdUyrNLtRhGc47cXcZtLG4crryfu44zE'
API='https://api.orca.so/v2/solana/pools/'+POOL
SITE=os.environ.get('LP_SITE','/workspace/paper_web/www/lp/data')
USDC='EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v'
Q=2**64; D=1e-3  # raw price = usd price * 1e6/1e9
def now(): return (datetime.datetime.utcnow()+datetime.timedelta(hours=7)).strftime('%Y-%m-%d %H:%M:%S WIB')
def get(u):
    r=urllib.request.Request(u,headers={'User-Agent':'Mozilla/5.0'})
    return json.load(urllib.request.urlopen(r,timeout=20))
def log(f,o): open(f,'a').write(json.dumps(o)+'\n')
def amounts(L,P,a,b):  # usd-price based; returns (sol,usdc) for liquidity L (raw units)
    s,sa,sb=math.sqrt(P*D),math.sqrt(a*D),math.sqrt(b*D); s=min(max(s,sa),sb)
    return L*(1/s-1/sb)/1e9, L*(s-sa)/1e6
def mkpos(usd,P,w):
    a,b=P*(1-w),P*(1+w); x,y=amounts(1e12,P,a,b); v=x*P+y
    return {'L':1e12*usd/v,'a':a,'b':b,'w':w,'fees':0.0,'out_since':None,'rebal':0,'rebal_cost':0.0,'basis':usd,'hodl_sol':usd/2/P,'hodl_usdc':usd/2}
def val(p,P): x,y=amounts(p['L'],P,p['a'],p['b']); return x*P+y
st=json.load(open('state.json')) if os.path.exists('state.json') else None
while True:
    try:
        d=get(API)['data']; P=float(d['price']); fr=d['feeRate']/1e6
        fgA,fgB=int(d['feeGrowthGlobalA']),int(d['feeGrowthGlobalB']); Lact=int(d['liquidity'])
        try: up=float(get('https://api.dexscreener.com/latest/dex/tokens/'+USDC)['pairs'][0]['priceUsd']) if False else None
        except: up=None
        # USDC peg: Orca USDT/USDC-independent check via Jupiter price
        try: up=float(get('https://lite-api.jup.ag/price/v3?ids='+USDC)[USDC]['usdPrice'])
        except Exception as e: up=None
        if st is None:
            st={'start':now(),'P0':P,'pool':POOL,'fee_rate':fr,'fgA':fgA,'fgB':fgB,'halted':False,
                'pos':{'narrow':mkpos(1000,P,0.10),'wide':mkpos(1000,P,0.25)}}
            log('events.jsonl',{'t':now(),'ev':'start','price':P,'ranges':{k:[round(v['a'],2),round(v['b'],2)] for k,v in st['pos'].items()}})
        dA,dB=(fgA-st['fgA'])%(2**128),(fgB-st['fgB'])%(2**128); st['fgA'],st['fgB']=fgA,fgB
        halt= up is not None and abs(up-1)>0.005
        if halt!=st['halted']: st['halted']=halt; log('events.jsonl',{'t':now(),'ev':'HALT usdc depeg' if halt else 'resume','usdc':up})
        row={'t':now(),'price':round(P,4),'usdc':up,'fee_rate':fr,'active_L':Lact,'tvl':round(float(d['tvlUsdc'])),'vol24h':round(float(d['stats']['24h']['volume'])),'halted':halt}
        for k,p in st['pos'].items():
            inr=p['a']<=P<=p['b']
            if inr and not halt:
                # real on-chain feeGrowthGlobal delta (fee per unit liquidity), scaled by our L, diluted by our own L
                f=p['L']*(dA/Q/1e9*P+dB/Q/1e6)*Lact/(Lact+p['L'])
                p['fees']+=f; p['out_since']=None
            elif not inr:
                p['out_since']=p['out_since'] or time.time()
                if time.time()-p['out_since']>1800 and not halt:
                    v=val(p,P); x,y=amounts(p['L'],P,p['a'],p['b']); swap=abs(x*P-v/2)
                    cost=swap*(fr+0.001)+0.01; v-=cost
                    n=mkpos(v,P,p['w']); 
                    for kk in ['fees','rebal','rebal_cost','basis','hodl_sol','hodl_usdc']: n[kk]=p[kk]
                    n['rebal']+=1; n['rebal_cost']+=cost; st['pos'][k]=p=n
                    log('events.jsonl',{'t':now(),'ev':'rebalance','pos':k,'price':P,'cost':round(cost,4),'new_range':[round(p['a'],2),round(p['b'],2)]})
            v=val(p,P); h=p['hodl_sol']*P+p['hodl_usdc']
            row[k]={'range':[round(p['a'],2),round(p['b'],2)],'in_range':inr,'value':round(v,2),'fees':round(p['fees'],4),'hodl':round(h,2),'il':round(v-h,2),'rebal':p['rebal'],'rebal_cost':round(p['rebal_cost'],4),'net_pnl':round(v+p['fees']-p['basis'],2),'vs_hodl':round(v+p['fees']-h,2)}
        log('ticks.jsonl',row); json.dump(st,open('state.json','w'))
        open(''+SITE+'/latest.json','w').write(json.dumps({'state':{'start':st['start'],'P0':st['P0'],'pool':POOL},'row':row}))
        os.system('cp events.jsonl '+SITE+'/ 2>/dev/null; tail -n 120 ticks.jsonl > '+SITE+'/ticks.jsonl')
    except Exception as e: print(now(),'err',e,flush=True)
    time.sleep(60)
