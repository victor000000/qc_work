"""Live status box from DB (server periodic emit gets starved)."""
import qc_storage as storage, os, time
from pathlib import Path
DATA = Path(os.environ.get("QC_DATA_DIR", Path(__file__).resolve().parents[1] / "data"))


def fmt(n):
    return f"{n:,}"


def gather(db, name):
    con = storage.connect(db, timeout=2)
    cur = con.cursor()
    cur.execute("SELECT status, COUNT(*) FROM backtest_queue GROUP BY status")
    s = dict(cur.fetchall())
    cur.execute("SELECT COUNT(*) FROM backtest_queue WHERE status='running' AND backtest_id IS NOT NULL")
    bt = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM experiments WHERE status='success'")
    exps = cur.fetchone()[0]
    return name, s.get('queued', 0), s.get('running', 0), bt, s.get('done', 0), s.get('failed', 0), exps


def main():
    pid_path = str(DATA / 'qc-server.pid')
    state, uptime = 'STOPPED', 0
    if os.path.exists(pid_path):
        pid = open(pid_path).read().strip()
        if os.path.exists(f'/proc/{pid}'):
            uptime = int(time.time() - os.path.getmtime(pid_path))
            state = 'RUNNING'
    h, m = uptime // 3600, (uptime % 3600) // 60

    s1 = gather(str(DATA / 'S001.duckdb'), 's001')
    s2 = gather(str(DATA / 'S002.duckdb'), 's002')
    busy = min(10, s1[2] + s2[2])

    def line(s):
        n, q, r, bt, d, f, e = s
        rd = f"{bt}/{r}" if bt < r else str(r)
        pct = d / max(d + f, 1) * 100
        return f"  {n:<5} Q:{q:<3} R:{rd:<7} D:{fmt(d):>8} F:{fmt(f):>5} exps:{fmt(e):>8} {pct:5.1f}%"

    w = 64

    def pad(s):
        diff = w - len(s)
        return f"│{s}{' ' * max(diff, 0)}│" if diff >= 0 else f"│{s[:w]}│"

    print(f"┌{'─' * w}┐")
    print(pad(f"  {state:<8} {h:>2}h {m:02}m   live snapshot   slots {busy}/10"))
    print(f"├{'─' * w}┤")
    for s in (s1, s2):
        print(pad(line(s)))
    print(f"└{'─' * w}┘")


if __name__ == '__main__':
    main()
