"""Frozen paired-session diagnostics, never a recipe-selection or IID test."""
import argparse
import json
import math
import random
from pathlib import Path
from statistics import mean, pstdev
from .pipeline import file_hash
from .audit_axis import acf, describe

METRICS=('bars','mean_duration_seconds','minute_variation_cv','return_acf1',
         'absolute_return_acf1','squared_return_acf1','absolute_return_p95')


def read_complete(folder):
    folder=Path(folder)
    manifest=json.loads((folder/'COMPLETE.json').read_text())
    if manifest.get('version')!='0.9.0' or manifest.get('complete') is not True:
        raise ValueError('completed 0.9.0 run required')
    expected=manifest['files']
    actual={p.name for p in folder.iterdir() if p.is_file() and p.name!='COMPLETE.json'}
    if set(expected)!=actual:raise ValueError('completion file inventory mismatch')
    for name,sha in expected.items():
        if Path(name).name!=name or file_hash(folder/name)!=sha:
            raise ValueError('completion hash mismatch')
    def rows(name):
        return [json.loads(line) for line in (folder/(name+'.jsonl')).read_text().splitlines()]
    return dict(report=json.loads((folder/'axis_quality.json').read_text()),
                sessions=rows('session_audit'),thresholds=rows('axis_thresholds'),bars=rows('axis_bars'),
                completion_sha256=file_hash(folder/'COMPLETE.json'))


def percentile(values,q):
    values=sorted(values)
    if not values:return None
    index=(len(values)-1)*q;lo=int(index);hi=math.ceil(index)
    return values[lo]+(values[hi]-values[lo])*(index-lo)


def session_metrics(bars):
    bars=sorted((b for b in bars if b['is_complete']),key=lambda b:b['sequence'])
    # A return exists only with a preceding completed close in this segment.
    groups={}
    for b in bars:
        if b['start_reference_close'] is not None:
            groups.setdefault(b['segment_id'],[]).append(math.log(b['close']/b['start_reference_close']))
    returns=[r for group in groups.values() for r in group]
    def dependence(transform):
        samples=[(len(v)-1,acf([transform(r) for r in v])) for v in groups.values() if len(v)>1]
        samples=[(n,v) for n,v in samples if v is not None]
        return sum(n*v for n,v in samples)/sum(n for n,v in samples) if samples else None
    variation=[b['minute_variation'] for b in bars]
    return dict(bars=len(bars),return_count=len(returns),
        mean_duration_seconds=mean(b['duration_seconds'] for b in bars) if bars else None,
        minute_variation_cv=pstdev(variation)/mean(variation) if variation and mean(variation)>0 else None,
        return_acf1=dependence(lambda r:r),absolute_return_acf1=dependence(abs),
        squared_return_acf1=dependence(lambda r:r*r),absolute_return_p95=percentile([abs(r) for r in returns],.95))


def paired_interval(differences,replicates=2000,seed=900):
    if len(differences)<2:return None
    rng=random.Random(seed)
    means=[mean(rng.choices(differences,k=len(differences))) for _ in range(replicates)]
    return [percentile(means,.025),percentile(means,.975)]


def compare(left,right,replicates=2000,seed=900):
    if not isinstance(replicates,int) or replicates<100:raise ValueError('at least 100 replicates required')
    a,b=read_complete(left),read_complete(right)
    for key in ('release','mode','underlying','calendar_hash','input_files','input_kind'):
        if a['report'][key]!=b['report'][key]:raise ValueError('incompatible runs: '+key)
    if a['report']['recipe']!='spy_close_volume' or b['report']['recipe']!='time_control':
        raise ValueError('frozen comparison requires SPY close-volume versus time control')
    if a['report']['underlying']!='SPY':raise ValueError('SPY control required')
    def eligible(run):
        calibrated={r['session'] for r in run['thresholds'] if r['threshold'] is not None and r['threshold']>0}
        nonempty={r['session'] for r in run['bars'] if r['is_complete']}
        return {r['session'] for r in run['sessions'] if r['complete']} & calibrated & nonempty
    common=sorted(eligible(a)&eligible(b))
    if len(common)<2:raise ValueError('insufficient common complete calibrated sessions')
    metrics=[]
    for day in common:
        metrics.append(dict(session=day,left=session_metrics([r for r in a['bars'] if r['session']==day]),
                            right=session_metrics([r for r in b['bars'] if r['session']==day])))
    summary={}
    for key in METRICS:
        pairs=[(r['left'][key],r['right'][key]) for r in metrics if r['left'][key] is not None and r['right'][key] is not None]
        diffs=[x-y for x,y in pairs]
        summary[key]=dict(paired_sessions=len(pairs),left_mean=mean(x for x,y in pairs) if pairs else None,
            right_mean=mean(y for x,y in pairs) if pairs else None,mean_difference=mean(diffs) if diffs else None,
            session_bootstrap_95=paired_interval(diffs,replicates,seed))
    midpoint=len(metrics)//2
    chronological=[]
    for label,part in [('earlier',metrics[:midpoint]),('later',metrics[midpoint:])]:
        chronological.append(dict(label=label,start=part[0]['session'],end=part[-1]['session'],sessions=len(part),
            mean_bar_difference=mean(r['left']['bars']-r['right']['bars'] for r in part)))
    distributions=[]
    for run in (a,b):
        selected=[r for r in run['bars'] if r['session'] in common and r['is_complete']]
        distributions.append(dict(recipe=run['report']['recipe'],bars=len(selected),
            activity_unit=selected[0]['threshold_unit'],
            activity=describe([r['activity'] for r in selected]),
            overshoot=describe([r['overshoot'] for r in selected]),
            duration_seconds=describe([r['duration_seconds'] for r in selected])))
    return dict(version='0.9.0',status='sampled_diagnostic' if a['report']['mode']=='sampled' else 'fixture_diagnostic',
        mode=a['report']['mode'],input_kind=a['report']['input_kind'],release=a['report']['release'],
        underlying='SPY',recipes=['spy_close_volume','time_control'],
        source_completion_sha256=[a['completion_sha256'],b['completion_sha256']],
        common_sessions=common,excluded_sessions=sorted({r['session'] for r in a['sessions']} - set(common)),
        per_session=metrics,paired_summary=summary,chronological=chronological,distributions=distributions,
        uncertainty=dict(method='paired whole-session bootstrap of session metrics',seed=seed,replicates=replicates),
        limitations=['Historical replication; recipes fixed before this comparison, all dates previously inspected.',
            'Session resampling preserves intraday structure but does not model dependence between days.',
            'Small session sample; confidence intervals are descriptive, not an IID or superiority test.',
            'Different event horizons; return-tail sizes are not directly comparable risk forecasts.',
            'SPY close-times-volume is approximate notional; no SPX or actual-dollar equivalence.'],
        recipe_selected=None,strict_acceptance=False,cloud_parity=False,economic_acceptance=False)


def main():
    p=argparse.ArgumentParser();p.add_argument('--left',required=True);p.add_argument('--right',required=True);p.add_argument('--out',required=True)
    args=p.parse_args();result=compare(args.left,args.right)
    with Path(args.out).open('x') as stream:json.dump(result,stream,indent=2,allow_nan=False);stream.write('\n')
    print(json.dumps(dict(common_sessions=len(result['common_sessions']),status=result['status'])))

if __name__=='__main__':main()
