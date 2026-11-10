"""Build an offline dashboard from the already verified Task 2 evidence."""
from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
RUN = ROOT / 'out/engineering_verified_20261110_final'


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def read_csv(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def build():
    summary = read_json(RUN / 'verification_summary.json')
    manifest = read_json(RUN / 'run_manifest.json')
    if not summary['validation_passed'] or manifest['status'] != 'passed':
        raise ValueError('The selected engineering run has not passed.')
    # Verify the original input and the displayed result tables before embedding.
    for name in ('global_fine.csv', 'region_fine.csv'):
        actual = hashlib.sha256((RUN / name).read_bytes()).hexdigest()
        if actual != summary['artifacts_sha256'][name]:
            raise ValueError('Modified verification table: ' + name)
    elements_path = ROOT / 'out/n28/constellation.csv'
    if hashlib.sha256(elements_path.read_bytes()).hexdigest() != manifest['elements_sha256']:
        raise ValueError('Constellation differs from the verified input.')

    cells = sorted(read_csv(RUN / 'global_fine.csv'),
                   key=lambda r: (float(r['lat_deg']), float(r['lon_deg'])))
    latitudes = sorted({float(r['lat_deg']) for r in cells})
    longitudes = sorted({float(r['lon_deg']) for r in cells})
    if len(cells) != len(latitudes) * len(longitudes):
        raise ValueError('The display requires the complete regular evaluation grid.')
    first = [float(r['first_access_s']) if r['first_access_s'] else None for r in cells]
    counts = [int(r['n_accesses']) for r in cells]
    metrics = summary['global_coverage']
    if sum(t is not None for t in first) != metrics['n_covered']:
        raise ValueError('Coverage table and summary differ.')
    native_comparison = read_json(ROOT / 'out/model_alignment/global_all_windows_comparison.json')
    if not native_comparison['ok']:
        raise ValueError('Full-window comparison has not passed.')
    region = [dict(sat=int(r['sat_id']), start=float(r['start_s']), stop=float(r['stop_s']))
              for r in read_csv(RUN / 'region_fine.csv')]
    elements = [dict(sat=int(r['sat_id']), altitude=float(r['h_km']),
                     inclination=float(r['inc_deg']), raan=float(r['raan_deg']),
                     phase=float(r['u_deg'])) for r in read_csv(elements_path)]
    stamp = datetime.fromisoformat(manifest['finished_utc']).astimezone(timezone(timedelta(hours=8)))
    data = dict(
        date=stamp.strftime('%Y-%m-%d'), epoch='2027-01-01 00:00 UTC',
        stop='2027-01-08 00:00 UTC', duration=604800, elements=elements,
        metrics=metrics, revisit=summary['region_revisit'], checks=summary['checks'],
        globalWindows=summary['native_access_rows_after_refinement'],
        allWindowComparison=native_comparison['max_endpoint_difference_s'],
        grid=dict(lat=latitudes, lon=longitudes, first=first, counts=counts),
        region=region, boundary=read_json(ROOT / 'data/official_region/yangtze_river_delta_boundary.geojson'),
        provenance=dict(input_sha256=manifest['elements_sha256'],
                        eop_sha256=manifest['profile']['eop_sha256'],
                        source_run='out/engineering_verified_20261110_final',
                        source_commit='7742b3b42bb7cc5cb65bbb3081f62caeef802197'),
    )
    template = (HERE / 'template.html').read_text(encoding='utf-8')
    if template.count('__TASK2_DATA__') != 1:
        raise ValueError('Expected exactly one data insertion point.')
    encoded = json.dumps(data, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
    encoded = encoded.replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    output = HERE / 'index.html'
    output.write_text(template.replace('__TASK2_DATA__', encoded), encoding='utf-8')
    print(f'Built {output.name}: {output.stat().st_size:,} bytes; '
          f'{len(cells):,} grid cells, {len(region)} regional windows.')


if __name__ == '__main__':
    build()
