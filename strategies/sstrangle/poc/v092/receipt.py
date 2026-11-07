"""Verify exported runtime statistics; integrity does not prove native origin."""
import argparse
from datetime import datetime
import hashlib
import json
import math
from .probe import validate_plan


def decode(stats, checkpoint):
    validate_plan([checkpoint])
    prefix = checkpoint['prefix']
    try:
        length_text = stats[prefix+'len']
        if not isinstance(length_text, str) or not length_text.isascii() or not length_text.isdecimal():
            raise ValueError('invalid length')
        length = int(length_text)
        if not 1 <= length <= 2880:
            raise ValueError('receipt length outside capacity')
        parts = [stats[prefix+str(i).zfill(2)] for i in range(16)]
        if any(not isinstance(part, str) or len(part) > 180 for part in parts):
            raise ValueError('invalid chunk')
        raw = ''.join(parts)[:length]
        if parts != [raw[i*180:(i+1)*180] or ' ' for i in range(16)]:
            raise ValueError('incomplete or noncanonical chunks')
        if stats[prefix+'sha256'] != hashlib.sha256(raw.encode()).hexdigest():
            raise ValueError('receipt checksum mismatch or publication incomplete')
        payload = json.loads(raw)
        required = {'time','phase','equity','cash','used','remaining','groups','holdings','requests'}
        if not isinstance(payload, dict) or set(payload) != required:
            raise ValueError('error, capacity or incomplete snapshot')
        time = datetime.fromisoformat(payload['time'])
        if time.tzinfo or not datetime.fromisoformat(checkpoint['start']) <= time <= datetime.fromisoformat(checkpoint['end']):
            raise ValueError('observation outside window')
        if payload['phase'] != checkpoint['phase']:
            raise ValueError('callback phase mismatch')
        def number(value):
            if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
                raise ValueError('nonfinite or invalid numeric value')
        def positions(rows, fields):
            if not isinstance(rows, list):
                raise ValueError('invalid positions')
            for row in rows:
                if not isinstance(row, dict) or set(row) != fields or not isinstance(row['symbol'], str) or not row['symbol']:
                    raise ValueError('invalid position')
                for key in fields - {'symbol'}:
                    number(row[key])
        for key in ('equity','cash','used','remaining'):
            number(payload[key])
        positions(payload['holdings'], {'symbol','quantity','value'})
        positions(payload['requests'], {'symbol','quantity'})
        if not isinstance(payload['groups'], list):
            raise ValueError('invalid groups')
        for group in payload['groups']:
            if not isinstance(group, dict) or set(group) != {'model','reserved','positions'} or not isinstance(group['model'], str) or not group['model']:
                raise ValueError('invalid group')
            number(group['reserved'])
            positions(group['positions'], {'symbol','quantity'})
        return payload
    except (KeyError, TypeError, OverflowError) as exc:
        raise ValueError('missing or malformed receipt') from exc


def verify(stats, plan):
    return {row['prefix']: decode(stats, row) for row in validate_plan(plan)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--statistics', required=True)
    parser.add_argument('--plan', required=True)
    args = parser.parse_args()
    from pathlib import Path
    print(json.dumps(verify(json.loads(Path(args.statistics).read_text()), json.loads(Path(args.plan).read_text())), indent=2))
