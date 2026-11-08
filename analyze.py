"""Reproduce the numbers in https://bnoc.xyz/t/198/13 from data/blocks/.

    python3 analyze.py            # summary
    python3 analyze.py --csv      # one row per mint block (the table in the post)

Delay of a block = median, over all pools except the one that mined it, of
each pool's first job on top of the block, in ms after the earliest pool
(raw stratum.work collector receive times). Blocks with fewer than 15 such
pools are dropped. Mint block: mempool.space audit lists >= 1,000 unseen
transactions. Normal block: <= 50. Blocks in between belong to neither group.
"""
import json, os, statistics as st, sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(HERE, 'data', 'blocks')
MINT, NORMAL, MIN_POOLS = 1000, 50, 15


def same(a, b):
    norm = lambda s: s.lower().replace(' ', '').replace('pool', '')
    return norm(a) == norm(b)


def delay(b, key='first_job_ms'):
    v = [p[key] for name, p in b['pools'].items() if p.get(key) is not None and not same(name, b['pool'])]
    return st.median(v) if len(v) >= MIN_POOLS else None


def controls(b, pool, key, tol, test):
    return [delay(n, key) for n in pool if test(n, b, tol) and delay(n, key) is not None]


by_size = lambda n, b, tol: abs(n['size'] - b['size']) <= tol * b['size']
by_tx = lambda n, b, tol: abs(n['tx_count'] - b['tx_count']) <= tol * b['tx_count']
by_pool_size = lambda n, b, tol: n['pool'] == b['pool'] and by_size(n, b, tol)


def gaps(mint, normal, test, tol, need, key='first_job_ms'):
    out = []
    for b in mint:
        c = controls(b, normal, key, tol, test)
        if len(c) >= need:
            out.append((b, delay(b, key) - st.median(c), c))
    return out


def summary(label, g):
    d = [x for _, x, _ in g]
    print(f'{label}: {sum(x > 0 for x in d)} of {len(d)} later, median {st.median(d):+.0f} ms, '
          f'range {min(d):+.0f} to {max(d):+.0f}')


if __name__ == '__main__':
    blocks = [json.load(open(os.path.join(D, f))) for f in sorted(os.listdir(D)) if f.endswith('.json')]
    blocks = [b for b in blocks if delay(b) is not None]
    mint = [b for b in blocks if b['unseen_txs'] >= MINT]
    normal = [b for b in blocks if b['unseen_txs'] <= NORMAL]
    size_gaps = gaps(mint, normal, by_size, 0.10, 5)

    if '--csv' in sys.argv:
        print('height,pool,tx_count,size_mb,unseen_txs,delay_ms,same_size_median_ms,controls,gap_ms,fees_below_template_pct')
        for b, gap, c in size_gaps:
            f = (b['expected_fees'] - b['fees']) / b['expected_fees'] * 100 if b.get('expected_fees') else ''
            print(f"{b['height']},{b['pool']},{b['tx_count']},{b['size'] / 1e6:.2f},{b['unseen_txs']},"
                  f"{delay(b):.0f},{st.median(c):.0f},{len(c)},{gap:+.0f},{f if f == '' else f'{f:.1f}'}")
        sys.exit()

    print(f'{len(blocks)} blocks {blocks[0]["height"]}-{blocks[-1]["height"]}: '
          f'{len(mint)} mint, {len(normal)} normal, {len(blocks) - len(mint) - len(normal)} in between (neither)')
    summary('same size (+-10 % bytes)', size_gaps)
    summary('same pool (+-15 % bytes, >= 3 controls)', gaps(mint, normal, by_pool_size, 0.15, 3))
    summary('same tx count (+-30 %)', gaps(mint, normal, by_tx, 0.30, 5))
    summary('first job with transactions, same size', gaps(mint, normal, by_size, 0.10, 5, 'first_filled_job_ms'))

    per_pool = defaultdict(list)
    for b, gap, _ in size_gaps:
        per_pool[b['pool']].append(gap)
    print('by mining pool:', ', '.join(f'{p} {st.median(v):+.0f} ms ({len(v)})' for p, v in per_pool.items()))

    print(f"median size: mint {st.median(b['size'] for b in mint) / 1e6:.2f} MB, "
          f"normal {st.median(b['size'] for b in normal) / 1e6:.2f} MB")
    ratio = [b['tx_count'] / st.median(n['tx_count'] for n in normal if by_size(n, b, 0.10))
             for b in mint if any(by_size(n, b, 0.10) for n in normal)]
    print(f'tx count vs same-size normal blocks: median {st.median(ratio):.1f}x; '
          f'{sum(b["tx_count"] > max(n["tx_count"] for n in normal) for b in mint)} mint blocks above '
          f'the largest normal block ({max(n["tx_count"] for n in normal):,} tx)')

    def below(group):
        v = [(b['expected_fees'] - b['fees']) / b['expected_fees'] * 100 for b in group if b.get('expected_fees')]
        return st.median(v), len(v)
    m, nm = below(mint)
    c, nc = below([b for b in normal if b.get('expected_fees')])
    print(f'fees below mempool.space audit template: mint {m:.1f} % ({nm}), size-matched normal {c:.1f} % ({nc})')
