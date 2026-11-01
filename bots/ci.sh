#!/bin/bash
# PAPER ONLY. Runs both bots ~5h40m, pushes dashboard data every 3 min, then chains next run.
R=$(pwd); export LP_SITE=$R/lp/data TZ=Asia/Jakarta
git config user.name paper-bot; git config user.email actions@users.noreply.github.com
(cd bots/memebot && while true; do python3 bot.py; sleep 10; done) &
(cd bots/lp && while true; do python3 bot.py; sleep 10; done) &
END=$(( $(date +%s) + 340*60 ))
sync(){ M=bots/memebot; mkdir -p data
 cp -f $M/summary.txt data/ 2>/dev/null
 python3 -c "import json;s=json.load(open('$M/state.json'));json.dump({k:s.get(k) for k in ('cash','pos')},open('data/state.json','w'))"
 for f in trades kills cycles; do [ -f $M/$f.jsonl ] && tail -n 30 $M/$f.jsonl > data/$f.jsonl; done
 for f in $M/kills.jsonl $M/cycles.jsonl $M/scores.jsonl $M/errors.jsonl bots/lp/ticks.jsonl; do [ -f $f ] && [ $(wc -l <$f) -gt 20000 ] && { tail -n 15000 $f > $f.t; mv $f.t $f; }; done
 date '+%F %T WIB' > data/updated.txt
 git add -A data lp bots index.html; git commit -qm "data $(date +%F_%T)" || return
 for i in 1 2 3; do git pull -q --rebase -X theirs origin main && git push -q origin main && break; sleep 5; done
 gh api -X POST repos/$GITHUB_REPOSITORY/pages/builds >/dev/null 2>&1 || true; }
while [ $(date +%s) -lt $END ]; do sleep 180; sync; done
kill $(jobs -p); sleep 3; sync
gh workflow run bots.yml --ref main -R $GITHUB_REPOSITORY
