"""Where the UNCOMMON•GOODS mints in the mint blocks go.

    python3 destinations.py [raw_dir]

For every mint block in data/blocks/ (>= 1,000 unseen transactions), fetch the
raw block from mempool.space (or read <raw_dir>/<height>.raw if present) and
look at each transaction carrying the runestone 6a5d0414011400. The minted
rune goes to the first output that is not OP_RETURN. When that output is P2A,
the next link of the mint chain spends it and the runes move on to that
link's first non-OP_RETURN output, until one pays an address. Prints the most
common addresses and how many blocks they appear in, and writes
data/mint-destinations.csv (one row per block and address).
"""
import collections, csv, hashlib, io, json, os, sys, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(HERE, 'data', 'blocks')
RUNESTONE = bytes.fromhex('6a5d0414011400')
P2A = bytes.fromhex('51024e73')
B32 = 'qpzry9x8gf2tvdw0s3jn54khce6mua7l'


def varint(f):
    b = f.read(1)[0]
    return b if b < 0xfd else int.from_bytes(f.read({0xfd: 2, 0xfe: 4, 0xff: 8}[b]), 'little')


def polymod(values):
    gen = [0x3b6a57b2, 0x26508e6d, 0x1ea119fa, 0x3d4233dd, 0x2a1462b3]
    chk = 1
    for v in values:
        top = chk >> 25
        chk = (chk & 0x1ffffff) << 5 ^ v
        for i in range(5):
            chk ^= gen[i] if (top >> i) & 1 else 0
    return chk


def segwit_address(spk):
    """bc1 address of a witness output script, None otherwise."""
    if len(spk) < 4 or spk[1] != len(spk) - 2 or not (spk[0] == 0 or 0x51 <= spk[0] <= 0x60):
        return None
    ver = 0 if spk[0] == 0 else spk[0] - 0x50
    data, acc, bits = [], 0, 0
    for x in spk[2:]:
        acc, bits = acc << 8 | x, bits + 8
        while bits >= 5:
            bits -= 5
            data.append(acc >> bits & 31)
    if bits:
        data.append(acc << (5 - bits) & 31)
    data = [ver] + data
    hrp = [ord(c) >> 5 for c in 'bc'] + [0] + [ord(c) & 31 for c in 'bc']
    pm = polymod(hrp + data + [0] * 6) ^ (1 if ver == 0 else 0x2bc830a3)
    return 'bc1' + ''.join(B32[x] for x in data + [(pm >> 5 * (5 - i)) & 31 for i in range(6)])


def txid(raw, start, body, body_end, locktime):
    """Txid: double SHA-256 of the transaction without its witness."""
    stripped = raw[start:start + 4] + raw[body:body_end] + raw[locktime:locktime + 4]
    return hashlib.sha256(hashlib.sha256(stripped).digest()).digest()[::-1]


def destinations(raw):
    """(number of mints, Counter of the addresses the mints end up at).

    A mint whose rune goes to P2A is followed down its chain: the next link
    spends that output, and runes nobody assigns move on to its own first
    non-OP_RETURN output, until one of them pays an address. Every chain in
    these blocks ends in the same block; one that does not is counted as
    'chain continues outside the block'.
    """
    f = io.BytesIO(raw)
    f.read(80)
    txs, order = {}, []
    for _ in range(varint(f)):
        start = f.tell()
        f.read(4)
        segwit = f.read(2) == b'\x00\x01'
        if not segwit:
            f.seek(-2, 1)
        body = f.tell()
        n_in, ins = varint(f), []
        for _ in range(n_in):
            prev = f.read(36)
            ins.append((prev[:32], int.from_bytes(prev[32:], 'little')))
            f.read(varint(f))
            f.read(4)
        outs = []
        for _ in range(varint(f)):
            f.read(8)
            outs.append(f.read(varint(f)))
        body_end = f.tell()
        if segwit:
            for _ in range(n_in):
                for _ in range(varint(f)):
                    f.read(varint(f))
        locktime = f.tell()
        f.read(4)
        tid = txid(raw, start, body, body_end, locktime) if segwit else \
            hashlib.sha256(hashlib.sha256(raw[start:f.tell()]).digest()).digest()[::-1]
        txs[tid] = (ins, outs)
        order.append(tid)
    spender = {(prev[::-1], i): t for t in order for prev, i in txs[t][0]}
    mints, dest = 0, collections.Counter()
    for t in order:
        if RUNESTONE not in txs[t][1]:
            continue
        mints += 1
        while True:
            outs = txs[t][1]
            k = next((j for j, s in enumerate(outs) if s[:1] != b'\x6a'), None)
            if k is None:
                break
            if outs[k] != P2A:
                dest[segwit_address(outs[k]) or outs[k].hex()] += 1
                break
            t = spender.get((t, k))
            if t is None:
                dest['chain continues outside the block'] += 1
                break
    return mints, dest


def raw_block(b, raw_dir):
    path = raw_dir and os.path.join(raw_dir, f"{b['height']}.raw")
    if path and os.path.exists(path):
        return open(path, 'rb').read()
    time.sleep(3)
    req = urllib.request.Request(f"https://mempool.space/api/block/{b['hash']}/raw",
                                 headers={'User-Agent': 'mint-switch-delay'})
    return urllib.request.urlopen(req, timeout=120).read()


if __name__ == '__main__':
    raw_dir = sys.argv[1] if len(sys.argv) > 1 else None
    blocks = [json.load(open(os.path.join(D, f))) for f in sorted(os.listdir(D)) if f.endswith('.json')]
    mint = [b for b in blocks if b['unseen_txs'] >= 1000]
    total, in_blocks, rows, n_mints = collections.Counter(), collections.Counter(), [], 0
    pools_of = collections.defaultdict(set)
    for b in mint:
        mints, dest = destinations(raw_block(b, raw_dir))
        n_mints += mints
        for addr, n in dest.most_common():
            total[addr] += n
            in_blocks[addr] += 1
            pools_of[addr].add(b['pool'])
            rows.append((b['height'], b['pool'], mints, addr, n))
    with open(os.path.join(HERE, 'data', 'mint-destinations.csv'), 'w', newline='') as out:
        w = csv.writer(out)
        w.writerow(['height', 'pool', 'mints_in_block', 'address', 'mints_to_address'])
        w.writerows(rows)
    print(f'{len(mint)} mint blocks, {n_mints:,} mints')
    for addr, n in total.most_common(6):
        print(f'{addr}  {n:,} mints ({n / n_mints:.0%}) in {in_blocks[addr]} blocks ({len(pools_of[addr])} pools)')
