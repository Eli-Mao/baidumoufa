# Project Status

Updated 2026-10-21 (Asia/Shanghai)

## Completed

- Copied the five local raw input files into `data/raw/` with matching SHA-256 hashes. The directory remains ignored by Git.
- Copied `de421.bsp` for Skyfield solar geometry.
- Fixed `satplan.config` to read `orbits.tle`, `stations.txt`, and `priority_*.txt`.
- All 35 repository tests pass, including the seven raw-data contract tests.
- Implemented chunked Skyfield/SGP4 propagation, UTC handling, station geometry, solar altitude, satellite illumination, sampled windows, edge bisection, window assembly, statistics, and a resumable CSV checkpoint.

## Current Evidence

- Parsed input: 10,000 unique satellites, 10 stations, priority counts 2024/3990/3986.
- TLE epochs: 2026-08-02 through 2026-08-04; planning period is 2026-10-01 through 2026-10-07 UTC. Results must retain the long-term extrapolation warning.
- The first real 100-target six-day run was started with 30-second candidate sampling and stopped after approximately 10 minutes CPU time because the serial Skyfield implementation was too slow for safe scaling. A partial `data/out/real_100/raw_checkpoint.csv` exists; it is not a completed experiment and must not be scored.

## Next Engineering Step

Replace the serial per-site propagation loop with vectorized time batches and bounded process workers, preserving the same physical predicates and checkpoint format. Re-run the 100-target experiment only after a small 1-target/10-station equivalence check passes.
