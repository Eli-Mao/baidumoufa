"""Whole-region contact calculation under QA E41; no regional evaluation grid."""
import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

from constellation import epoch_jd
from region import load_geojson
from run_sim import load_elements

OFFICIAL_REGION = Path(__file__).resolve().parent/'data/official_region/yangtze_river_delta_boundary.geojson'


def main():
    from continuous_region import simulate_region
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--elements', required=True)
    p.add_argument('--region', default=str(OFFICIAL_REGION))
    p.add_argument('--out', required=True)
    p.add_argument('--days', type=float, default=7)
    p.add_argument('--step', type=float, default=.03125)
    p.add_argument('--tolerance', type=float, default=.01)
    p.add_argument('--geometry-model',choices=['stk','sphere'],default='stk')
    p.add_argument('--eop',help='Frozen EOP file; defaults to the validated snapshot')
    a=p.parse_args()
    out=Path(a.out); out.parent.mkdir(parents=True,exist_ok=True)
    result=simulate_region(load_elements(a.elements),epoch_jd(),load_geojson(a.region),
                           days=a.days,step=a.step,tolerance_s=a.tolerance,
                           geometry_model=a.geometry_model,eop_path=a.eop,
                           progress=lambda sid,n: print(f'Satellite {sid}: {n} windows so far',flush=True))
    intervals=result.pop('access_intervals')
    pd.DataFrame(intervals,columns=['sat_id','start_s','stop_s']).to_csv(out.with_suffix('.csv'),index=False)
    result.update(region_file=str(Path(a.region).resolve()),
                  region_sha256=hashlib.sha256(Path(a.region).read_bytes()).hexdigest(),
                  qa_source='data/qa/task2_qa.json: E41, E45, E49',stk_verified=False,
                  access_csv=out.with_suffix('.csv').name)
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
