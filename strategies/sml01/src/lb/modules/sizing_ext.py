"""sizing_ext — VAL sizing engine EXTENSION module (separate QC project file, 2026-06-10).

Moved VERBATIM out of templates/footer.py.tmpl: the GLD/UUP ensemble main.py renders sat
39 bytes under QC's 64,000-byte/file wall, blocking all future footer work. _size() is the
RENDER-TIME sizing rule shared semantically with templates/infer.py.tmpl (which keeps its
own self-contained copy — infer renders standalone, no extra files); _cstats_sized() is the
VAL scorer. CONFIG is injected by the footer at import time (sizing_ext.CONFIG = CONFIG)
because _cstats_sized reads CONFIG["rebal_band"]/CONFIG.get("aim_a"). Any change here MUST
mirror infer.py.tmpl's _size to keep the VAL == OOS rule identity.
"""
import math

import numpy as np

CONFIG = {}   # injected by the footer before any _cstats_sized call


_VOL_FAST = 10
_VOL_SLOW = 60


def _size(p, thresh, sizing, rbuf):
    """Return target weight in [0,1] for prob p under the named sizing mode.
      ramp        = min(1,(p-thresh)*200) if p>thresh else 0          (legacy)
      binary      = 1.0 if p>thresh else 0.0                          (label-responsive)
      cdf_plain   = clip(2*Phi((p-thresh)/sqrt(p(1-p)))-1,0,1) if p>thresh else 0
      cdf_overlay = cdf_plain * clip(std_slow/std_fast, 0.6, 1.0)     (vol-targeted)
      longshort   = +1 if p>thresh, -1 if p<1-thresh, else 0          (SHORT-capable)
      ls_cdf      = clip(2*Phi((p-.5)/sqrt(p(1-p)))-1, -1, 1)         (continuous long/short)
    """
    if sizing == "crashveto":          # tail-risk veto: full long unless a crash is predicted (p_crash > thresh) -> flat
        return 0.0 if p > thresh else 1.0
    if sizing == "short_carry":        # variance-risk-premium CARRY harvest (VIXY/VXX): full SHORT to earn the
        return 0.0 if p > thresh else -1.0   # VIX-future roll decay, FLAT when an up-spike is predicted (p>thresh). Inverse of crashveto.
    if sizing == "crashsoft":          # SOFT crash-sizer (the crashveto cliff fix, SPY lead R876): full long
        lo = 0.5 * thresh              # while p_crash <= lo, linear de-lever lo->thresh, flat at p >= thresh.
        if p <= lo:                    # Smooth ramp -> partial rebalances (trades>80 reachable) and no
            return 1.0                 # single-threshold cliff (the lead's 2.53-vs-0.84 fragility).
        return float(max(0.0, (thresh - p) / (thresh - lo)))
    if sizing == "crashlean":          # GENTLE continuous crash-de-risk (the crashsoft cliff-fix): stay full
        return float(min(1.0, max(0.3, 1.0 - 1.5 * p)))   # long until crash risk p rises, then LEAN down
                                       # proportionally (0.3 floor keeps drift) — loses far less drift on a
                                       # false positive than crashsoft's full exit. For crash/dd labelers.
    if sizing == "tilt_up":            # LEVER-UP tilt (equity-index structural-barrier mirror, 2026-06-11):
        if p <= thresh:                # NEVER below 1.0x (keep ALL drift — the de-lever bracket proved
            return 1.0                 # any drift forfeit loses); lean UP to 1.5x only when the signal
        pp = min(max(p, 1e-6), 1.0 - 1e-6)   # is favorable. w = 1 + 0.5*cdf_bet(p,thresh).
        zu = (pp - thresh) / math.sqrt(pp * (1.0 - pp))
        bu = 2.0 * 0.5 * (1.0 + math.erf(zu / math.sqrt(2.0))) - 1.0
        return float(1.0 + 0.5 * min(1.0, max(0.0, bu)))
    if sizing == "tilt":               # LONG-ANCHORED drift tilt (equity-index reversion monetization,
        return float(max(0.5, min(1.0, 0.5 + p)))   # 2026-06-11): full long at p>=0.5, lean down to a 0.5 FLOOR as the
                                       # model predicts a down-wiggle. Keeps the drift (the only money on
                                       # indices) and harvests the auc~0.95 reversion signal as a LEAN,
                                       # not an in/out gate (in/out loses the drift and pays costs).
    if sizing == "kelly_dd":           # DRAWDOWN-CAPPED Kelly (backlog #13, Busseti-Boyd RCK simplified):
        if p <= thresh:                # binary-payoff Kelly f*=2p-1, shrunk by lam = ln(beta)/ln(alpha)
            return 0.0                 # for the constraint P(DD>20%) < 5% (lam ~= 1.857 — a CONSTANT,
        return float(min(1.0, max(0.0, (2.0 * p - 1.0) / 1.857)))  # no fitted params => leak-trivial,
                                       # VAL==OOS identical). The only theory-motivated sizing challenger.
    if sizing == "longshort":
        return 1.0 if p > thresh else (-1.0 if p < 1.0 - thresh else 0.0)
    if sizing in ("ls_cdf", "ls_overlay"):
        pp = min(max(p, 1e-6), 1.0 - 1e-6)
        zc = (pp - 0.5) / math.sqrt(pp * (1.0 - pp))
        w = float(min(1.0, max(-1.0, 2.0 * 0.5 * (1.0 + math.erf(zc / math.sqrt(2.0))) - 1.0)))
        if sizing == "ls_overlay":              # vol-target the long/short magnitude, keep sign (causal)
            m = len(rbuf)
            if m >= _VOL_FAST + 2:
                fast = float(np.std(rbuf[-_VOL_FAST:]))
                slow = float(np.std(rbuf[-min(m, _VOL_SLOW):]))
                if fast > 1e-9:
                    w *= float(min(1.0, max(0.45, slow / fast)))
        return w
    if sizing == "binary":
        return 1.0 if p > thresh else 0.0
    if sizing == "ramp":
        return float(min(1.0, (p - thresh) * 200.0)) if p > thresh else 0.0
    if sizing == "lever3":              # CONSTANT 3x leverage on the directional cdf bet: ~3x long when the
        if p <= thresh:                 # signal is confident, FLAT when it de-risks. Amplifies the steady
            return 0.0                  # uptrend capture (unlike vol-ratio leverage). LEAK-FREE but leveraged
        pp = min(max(p, 1e-6), 1.0 - 1e-6)   # 3x and NOT deflation-robust — a real number, high-risk, not a robust edge.
        z = (pp - thresh) / math.sqrt(pp * (1.0 - pp))
        bb = 2.0 * 0.5 * (1.0 + math.erf(z / math.sqrt(2.0))) - 1.0
        return float(min(3.0, 3.0 * max(0.0, bb)))
    if p <= thresh:
        return 0.0
    pp = min(max(p, 1e-6), 1.0 - 1e-6)
    z = (pp - thresh) / math.sqrt(pp * (1.0 - pp))
    b = 2.0 * 0.5 * (1.0 + math.erf(z / math.sqrt(2.0))) - 1.0  # 2*Phi(z)-1
    b = float(min(1.0, max(0.0, b)))
    if sizing == "cdf_overlay":
        m = len(rbuf)
        if m >= _VOL_FAST + 2:
            fast = float(np.std(rbuf[-_VOL_FAST:]))
            slow = float(np.std(rbuf[-min(m, _VOL_SLOW):]))
            if fast > 1e-9:
                b *= float(min(1.0, max(0.6, slow / fast)))
    if sizing == "dd_overlay":          # drawdown-aware: throttle the bet when the asset is
        m = len(rbuf)                   # underwater vs its recent rolling peak (causal, rbuf only)
        if m >= _VOL_FAST + 2:
            win = np.asarray(rbuf[-min(m, _VOL_SLOW):], dtype=float)
            cum = np.cumsum(win)                       # recent log-equity of the asset
            dd = float(cum[-1] - float(np.max(cum)))   # <= 0: current log DD from recent peak
            ref = 3.0 * float(np.std(win)) * math.sqrt(len(win))   # vol-normalized DD scale (~3σ)
            if ref > 1e-9:
                b *= float(min(1.0, max(0.5, 1.0 + dd / ref)))     # 1.0 at peak -> 0.5 floor when deep
    if sizing == "cond_es":             # CONDITIONAL EXPECTED-SHORTFALL sizing (Wang joint-dist talk):
        m = len(rbuf)                   # throttle the cdf bet when the asset's RECENT left-tail loss
        if m >= _VOL_FAST + 2:          # (fast ES) spikes above its baseline (slow ES). ES_q = mean of
            ff = sorted(rbuf[-_VOL_FAST:])                 # the worst q-fraction of returns; tail-focused —
            ss = sorted(rbuf[-min(m, _VOL_SLOW):])         # the asymmetric-risk analog of cdf_overlay's std ratio.
            kf = max(1, int(0.2 * len(ff)))                # causal (rbuf only): rbuf holds returns up to i-1.
            ks = max(1, int(0.2 * len(ss)))
            es_fast = -sum(ff[:kf]) / kf                   # >0 = avg loss across the worst kf recent returns
            es_slow = -sum(ss[:ks]) / ks
            if es_fast > 1e-9 and es_slow > 0.0:
                b *= float(min(1.0, max(0.4, es_slow / es_fast)))   # 1.0 calm -> 0.4 floor when tail spikes
    if sizing == "ddbreaker":           # dd_overlay's smooth throttle + a HARD circuit-breaker: go FLAT
        m = len(rbuf)                   # on EXTREME drawdown (frac<0.4) to cut the TAIL (MaxDD), re-enter
        if m >= _VOL_FAST + 2:          # on recovery. Attacks the Calmar denominator harder than the
            win = np.asarray(rbuf[-min(m, _VOL_SLOW):], dtype=float)   # 0.5-floor smooth throttle. Causal (rbuf only).
            cum = np.cumsum(win)
            dd = float(cum[-1] - float(np.max(cum)))
            ref = 3.0 * float(np.std(win)) * math.sqrt(len(win))
            if ref > 1e-9:
                frac = 1.0 + dd / ref
                b = 0.0 if frac < 0.4 else b * float(min(1.0, max(0.4, frac)))
    if sizing == "voltarget":           # TWO-SIDED vol-target (risk-parity): the cdf_overlay slow/fast
        m = len(rbuf)                   # ratio with the cap RAISED above 1.0 -> lever UP in calm (fast<slow)
        if m >= _VOL_FAST + 2:          # and de-lever in stress (fast>slow). Boosts CAGR in the calm trend
            fast = float(np.std(rbuf[-_VOL_FAST:]))      # AND cuts MaxDD as vol rises through a decline.
            slow = float(np.std(rbuf[-min(m, _VOL_SLOW):]))   # Causal (rbuf only) — leak-safe, same as cdf_overlay.
            if fast > 1e-9:
                b *= float(min(1.8, max(0.35, slow / fast)))
    if sizing == "levervt":             # HIGH-LEVERAGE two-sided vol-target: voltarget with the cap raised
        m = len(rbuf)                   # to 4x (floor 0.2x) -> amplifies the calm-uptrend capture to reach a
        if m >= _VOL_FAST + 2:          # high Calmar. LEAK-FREE (trailing rbuf only) but RISKY/leveraged and
            fast = float(np.std(rbuf[-_VOL_FAST:]))         # NOT deflation-robust — a real number, not a robust edge.
            slow = float(np.std(rbuf[-min(m, _VOL_SLOW):]))
            if fast > 1e-9:
                b *= float(min(4.0, max(0.2, slow / fast)))
    if sizing == "trend_gate":          # SLOW 200-bar (=200-DAY on the `daily` axis) MA trend gate
        m = len(rbuf)                   # (deep-review #1): cdf_overlay vol-target, then go FLAT when the
        if m >= _VOL_FAST + 2:          # reconstructed log-price is below its 200-bar trailing mean. Dodges
            fast = float(np.std(rbuf[-_VOL_FAST:]))         # the slow Feb-Apr 2025 decline by REACTING to realized
            slow = float(np.std(rbuf[-min(m, _VOL_SLOW):]))  # price (no forecast). LEAK-FREE: rbuf = causal returns
            if fast > 1e-9:             # up to i-1. Long during warmup (< 200 bars). L=200 frozen (no fit).
                b *= float(min(1.0, max(0.6, slow / fast)))
        if m >= 200:
            _lp = np.cumsum(np.asarray(rbuf, dtype=float))
            if _lp[-1] <= float(np.mean(_lp[-200:])):
                b = 0.0
    if sizing == "trendlev":            # LEVERAGED trend gate (deep-review #3): 3x the long bet while ABOVE
        m = len(rbuf)                   # the 200-bar MA, FLAT below. Levers the confirmed up-regime (CAGR up)
        if m >= 200:                    # while the gate keeps MaxDD off the SLOW declines. LEAK-FREE (causal
            _lp = np.cumsum(np.asarray(rbuf, dtype=float))   # rbuf) but leveraged/risky — the un-dodgeable fast
            if _lp[-1] <= float(np.mean(_lp[-200:])):        # V-dip (Aug-2024) is amplified, so NOT deflation-robust.
                return 0.0
        return float(min(3.0, 3.0 * b))
    if sizing == "trendlev_vt":         # VOL-TARGETED leveraged trend gate: 3x above the 200-bar MA but
        m = len(rbuf)                   # DE-LEVERED in stress (cuts the leveraged Aug-2024 fast-dip tail and
        if m >= 200:                    # trades continuously -> deployable), FLAT below the MA. Leak-free.
            _lp = np.cumsum(np.asarray(rbuf, dtype=float))
            if _lp[-1] <= float(np.mean(_lp[-200:])):
                return 0.0
        w = 3.0
        if m >= _VOL_FAST + 2:
            fast = float(np.std(rbuf[-_VOL_FAST:]))
            slow = float(np.std(rbuf[-min(m, _VOL_SLOW):]))
            if fast > 1e-9:
                w *= float(min(1.0, max(0.2, slow / fast)))
        return float(min(3.0, w * b))
    if sizing == "trendlev_dd":         # 3x above the 200-bar MA, flat below, PLUS a fast drawdown circuit-breaker
        m = len(rbuf)                   # (flat on frac<0.4) to cut the leveraged Aug-2024 fast-V-dip tail. Leak-free.
        if m >= 200:
            _lp = np.cumsum(np.asarray(rbuf, dtype=float))
            if _lp[-1] <= float(np.mean(_lp[-200:])):
                return 0.0
        w = 3.0 * b
        if m >= _VOL_FAST + 2:
            win = np.asarray(rbuf[-min(m, _VOL_SLOW):], dtype=float)
            cum = np.cumsum(win)
            dd = float(cum[-1] - float(np.max(cum)))
            ref = 3.0 * float(np.std(win)) * math.sqrt(len(win))
            if ref > 1e-9:
                frac = 1.0 + dd / ref
                w = 0.0 if frac < 0.4 else w * float(min(1.0, max(0.3, frac)))
        return float(min(3.0, w))
    return b


def _cstats_sized(probs, lc_arr, log_rets, thresh, sizing, tc=0.0005):
    """realistic_cstats variant that sizes via _size() (CONFIG['sizing']).
    Mirrors trainer.realistic_cstats accounting (decide-then-append causal rbuf,
    0.01 rebalance dead-band, tc on |delta|). Returns (calmar,trades,tot,mdd,ann,da)."""
    n = min(len(probs) - 1, len(log_rets) - 1, len(lc_arr) - 1)
    if n < 2:
        return 0, 0, 0, 0, 0, 0.0
    positions = np.zeros(n + 1)
    last_pos = 0.0
    trades = 0
    rbuf = []
    _aim_a = float(CONFIG.get("aim_a", 0.3))   # Garleanu-Pedersen partial-adjustment coefficient
    # 'aim' wraps a BASE sizing: partial-adjust toward that overlay's per-bar target. aim=plain CDF
    # bet; aim_dd=over dd_overlay (keep drawdown protection + cut turnover); aim_cdf=over cdf_overlay.
    _AIM_BASE = {"aim": "cdf_plain", "aim_dd": "dd_overlay", "aim_cdf": "cdf_overlay"}
    for i in range(n):
        _sz = _AIM_BASE.get(sizing, sizing)
        target = _size(float(probs[i]), thresh, _sz, rbuf)
        if sizing in _AIM_BASE:                # trade PARTIALLY toward the (overlaid) aim (Garleanu-Pedersen 2013):
            target = (1.0 - _aim_a) * last_pos + _aim_a * target   # x_t=(1-a)x_{t-1}+a*aim -> cuts turnover, keeps base overlay
        # Abs-delta dead-band — mirrors infer.py's rebalance band so val turnover/cost
        # matches OOS for long/short sizings too (the old long-only-flavoured condition
        # under-counted short flips).
        if abs(target - last_pos) > CONFIG["rebal_band"]:
            trades += 1
        positions[i] = target
        last_pos = target
        if i - 1 >= 0:
            rbuf.append(float(log_rets[i - 1]))
    if trades < 2:
        return 0, trades, 0, 0, 0, 0.0
    strat_rets = positions[:-1] * log_rets[1:n + 1]
    for i in range(1, n):
        if abs(positions[i] - positions[i - 1]) > CONFIG["rebal_band"]:
            strat_rets[i] -= tc * abs(positions[i] - positions[i - 1])
    cum = np.cumsum(strat_rets)                       # cumulative log-return == log-equity
    peak = np.maximum.accumulate(cum)
    dd = cum - peak                                   # log drawdown (<= 0)
    # COMPOUNDED metric, to match the REAL OOS estimator (QC 'Compounding Annual
    # Return' / 'Drawdown'): val must use the SAME definition as the keep gate, else
    # the synth selector reads systematically higher than OOS and is not a faithful
    # preview. (The residual val<->OOS gap after this is honest realism: OOS holds
    # continuously across minutes + overnight with real fees.)
    mdd = 1.0 - float(np.exp(float(np.min(dd))))      # max drawdown as a fraction
    if mdd < 1e-9:
        mdd = 1e-9
    cagr = float(np.exp(float(cum[-1]) * (880.0 / n))) - 1.0   # compounded annual return
    da = float(np.sum(1.0 - np.exp(dd)))              # compounded underwater area
    cal = cagr / mdd if mdd > 0.001 else 0
    return cal, trades, float(np.sum(strat_rets)), mdd, cagr, da


def _venn_abers(cal_s, cal_y, test_s):
    """Inductive Venn-Abers calibration (Vovk-Petej 2014; deep-v2 B4). For each test score s*, fit
    isotonic on the calibration set with (s*,0) appended -> p0 and with (s*,1) appended -> p1; the
    VA probability is p1/(1-p0+p1). Provably better-calibrated than a single isotonic fit (a
    multiprobability merge). Runs ONCE in the footer (post-training), reuses the embargoed-VAL
    calibration set; the resulting probs are saved + replayed by infer exactly like isotonic's."""
    from sklearn.isotonic import IsotonicRegression
    cs = np.asarray(cal_s, dtype=float)
    cy = np.asarray(cal_y, dtype=float)
    out = np.empty(len(test_s), dtype=float)
    base0 = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
    for i, s in enumerate(test_s):
        s = float(s)
        g0 = base0.fit(np.append(cs, s), np.append(cy, 0.0))
        p0 = float(g0.predict([s])[0])
        g1 = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0).fit(np.append(cs, s), np.append(cy, 1.0))
        p1 = float(g1.predict([s])[0])
        den = 1.0 - p0 + p1
        out[i] = (p1 / den) if den > 1e-9 else p1
    return out
