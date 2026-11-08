"""Fetch per-block data from mempool.space and stratum.work into data/blocks/.

    python3 collect.py <from_height> [to_height]

For each block H: pool, tx count, size and unseen transactions (mempool.space
audit), fees and the audit template's expected fees, and for every pool on
stratum.work its first job on top of H (and its first job carrying
transactions), in ms after the earliest pool. Jobs are taken from
mining-notify?height=H+1 and kept only if their prevhash is H in any of the
byte orders stratum uses. Blocks already in data/blocks/ are skipped. Slow on
purpose (a few seconds per request).
"""
import json, os, sys, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'data', 'blocks')
PAUSE = 3


def get(url):
    for attempt in range(3):
        time.sleep(PAUSE * (1 + 3 * attempt))
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'mint-switch-delay'})
            return json.loads(urllib.request.urlopen(req, timeout=90).read(), strict=False)
        except Exception:
            if attempt == 2:
                raise


def spellings(h):
    """A block hash as it can appear in a stratum prevhash."""
    b = bytes.fromhex(h)
    words = [b[i:i + 4] for i in range(0, 32, 4)]
    swapped = b''.join(w[::-1] for w in words)
    return {h, b[::-1].hex(), swapped.hex(), b''.join(words[::-1]).hex(), swapped[::-1].hex()}


def block(h, tip):
    info = get(f'https://mempool.space/api/v1/blocks/{h}')[0]
    assert info['height'] == h
    audit = get(f'https://mempool.space/api/v1/block/{info["id"]}/audit-summary')
    jobs = get(f'https://stratum.work/api/mining-notify?height={h + 1}')
    match = spellings(info['id'])
    first, filled = {}, {}
    for j in jobs:
        if j['prev_hash'].lower() not in match:
            continue
        t, p = int(j['timestamp'], 16), j['pool_name']
        if p not in first or t < first[p][0]:
            first[p] = (t, not j['merkle_branches'])
        if j['merkle_branches'] and (p not in filled or t < filled[p]):
            filled[p] = t
    t0 = min((t for t, _ in first.values()), default=0)
    return {
        'height': h, 'hash': info['id'], 'pool': info['extras']['pool']['name'],
        'tx_count': info['tx_count'], 'size': info['size'],
        'unseen_txs': len(audit.get('unseenTxs', [])),
        'fees': info['extras']['totalFees'], 'expected_fees': audit.get('expectedFees'),
        'pools': {p: {'first_job_ms': round((t - t0) / 1e6, 1), 'first_job_empty': empty,
                      'first_filled_job_ms': round((filled[p] - t0) / 1e6, 1) if p in filled else None}
                  for p, (t, empty) in first.items()},
    }


if __name__ == '__main__':
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    os.makedirs(OUT, exist_ok=True)
    tip = int(urllib.request.urlopen('https://mempool.space/api/blocks/tip/height').read())
    lo = int(sys.argv[1])
    hi = int(sys.argv[2]) if len(sys.argv) > 2 else tip - 2  # stratum.work needs the next block
    for h in range(lo, hi + 1):
        path = os.path.join(OUT, f'{h}.json')
        if os.path.exists(path):
            continue
        try:
            json.dump(block(h, tip), open(path, 'w'), indent=1)
            print(h, flush=True)
        except Exception as e:
            print(h, 'error:', e, flush=True)
