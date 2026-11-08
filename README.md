# mint-switch-delay

Data and scripts behind [bnoc.xyz/t/198/13](https://bnoc.xyz/t/198/13): how much later pools put out their
first job on top of blocks full of transactions the network hadn't seen (the UNCOMMON•GOODS P2A mint wave,
Nov 3–8, 2026), compared with normal blocks.

![Delay vs block size](delay-vs-size.png)

- `data/blocks/` – one JSON file per block, 974,540–975,028 (488 blocks)
- `analyze.py` – reproduces every number in the post (`python3 analyze.py`, or `--csv` for the table)
- `mint-blocks.csv` – the 41 mint blocks, as in the post's table
- `collect.py` – fetches more blocks from the public APIs (`python3 collect.py <from> [to]`)
- `destinations.py` – where the mints in the 41 mint blocks go (fetches the raw blocks from mempool.space);
  writes `data/mint-destinations.csv`

**Mint destinations.** A transaction counts as a mint if it carries the runestone `6a5d0414011400`. The rune
goes to its first output that isn't OP_RETURN. If that is P2A, the next link in the chain spends it and the
runes move on; every chain ends at an address in the same block. Across the 41 blocks, 54 % of all mints end
at `bc1qq9qx0jj6glxe7dcgj98uke8yr4ze7sadt2qjgj` (40 blocks) and 28 % at
`bc1qmcvv20xmujhhelyas5r59gkgvl92dhdwr9v4t4` (33 blocks).

**Method.** For block H, jobs come from `stratum.work/api/mining-notify?height=H+1`, kept if their prevhash
is H. Each pool's first job is measured from the earliest pool, and a block's delay is the median over all
pools except the one that mined it (at least 15 pools). These are raw collector receive times without latency
correction, so they show what stratum.work's collectors see, not the pools' internal timing. Mint block:
mempool.space's audit lists 1,000 or more unseen transactions. Normal block: 50 or fewer. The 12 blocks in
between belong to neither group.

**Not in here.** The kB fetched via getblocktxn come from my own node and can't be reproduced from public
data.

Sources: [stratum.work](https://stratum.work) and [mempool.space](https://mempool.space) APIs. Scripts: MIT.
