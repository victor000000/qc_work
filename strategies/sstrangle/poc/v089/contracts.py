"""Consumer gates: calendar structure and immutable provider attestations."""
from zoneinfo import ZoneInfo
from .axis import utc


def validate_calendar(calendar):
    previous=None;by_day={}
    for r in calendar:
        op,cl=utc(r['open']),utc(r['close']);day=r['session']
        if (cl<=op or (cl-op).total_seconds()%60 or
            op.astimezone(ZoneInfo('America/New_York')).date().isoformat()!=day or
            cl.astimezone(ZoneInfo('America/New_York')).date().isoformat()!=day or
            day in by_day or (previous and op<=previous)):
            raise ValueError('invalid calendar identity or overlap')
        by_day[day]=r;previous=cl
    if not by_day:raise ValueError('empty calendar')
    return by_day


def validate_receipt(manifest, receipt):
    if receipt.get('status')!='verified' or receipt.get('release')!=manifest['release']:
        raise ValueError('receipt does not attest this verified release')
    if receipt.get('frequency_seconds')!=60 or receipt.get('artifacts')!={k:v['sha256'] for k,v in manifest['files'].items()}:
        raise ValueError('receipt artifact binding mismatch')
    fixture=manifest.get('input_kind')=='synthetic_fixture'
    if fixture != (receipt.get('synthetic') is True):raise ValueError('fixture/provider identity mismatch')
    if not fixture:
        if manifest.get('data_state') not in ('staged','published'):raise ValueError('provider state required')
        if (manifest['data_state']=='published') != (receipt.get('canonical_publication') is True):
            raise ValueError('publication state mismatch')
        if not receipt.get('coverage') or not receipt.get('calendar_verified'):
            raise ValueError('provider coverage and calendar verification required')


def validate_strict_provider(manifest, receipt, mode):
    if mode=='strict' and manifest.get('input_kind')!='synthetic_fixture':
        if manifest.get('data_state')!='published' or receipt.get('strict_replay_ready') is not True:
            raise ValueError('strict provider replay not ready')
