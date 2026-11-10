"""Validate native saved STK sampling, independently of COM property readback."""
from pathlib import Path
import re
import math
import hashlib
from datetime import date,timedelta


def native_eop_binding(run,package,manifest):
    name=manifest.get('eop_file')
    if not name:return dict(frozen=False)
    run,package=Path(run),Path(package)
    text=(run/'Task2_Constellation.sc').read_text(encoding='utf-8-sig')
    m=re.search(r'^\s*EOPFilename\s+(.*?)\s*$',text,re.M)
    if not m or Path(m[1].strip('"')).name!=name:
        raise ValueError('native scene uses a different EOP file')
    a,b=(run/name).read_bytes(),(package/name).read_bytes()
    if a!=b:raise ValueError('native EOP snapshot differs from scene package')
    dates={date(*map(int,m)) for m in re.findall(r'^(\d{4}) (\d{2}) (\d{2}) ',a.decode('ascii'),re.M)}
    required={date(2027,1,1)+timedelta(days=d) for d in range(8)}
    if not required.issubset(dates):raise ValueError('EOP data does not cover the scenario interval')
    return dict(frozen=True,scenario_dates_present=True,filename=name,
                sha256=hashlib.sha256(a).hexdigest(),updated=a.decode('ascii').splitlines()[1],
                scenario_dates_are_predictions=manifest['eop_provenance']['scenario_dates_are_predictions'])


def native_region_sampling(path, manifest, step):
    text=Path(path).read_text(encoding='utf-8-sig')
    blocks=re.findall(r'(?ms)^BEGIN Access\s*\n(.*?)^END Access\s*$',text)
    expected={(int(s),c) for s in manifest['satellite_ids'] for c in manifest['region_area_targets']}
    found=set()
    for block in blocks:
        sat=re.search(r'/Satellite/SAT_(\d+)/Sensor/Cam\s*$',block,re.M)
        area=re.search(r'/AreaTarget/(\S+)\s*$',block,re.M)
        if not sat or not area: raise ValueError('unexpected native access pair')
        pair=(int(sat[1]),area[1])
        if pair in found: raise ValueError('duplicate native access pair')
        found.add(pair)
        def number(name):
            m=re.search(r'^\s*'+name+r'\s+(\S+)\s*$',block,re.M)
            if not m: raise ValueError('native access omits '+name)
            value=float(m[1])
            if not math.isfinite(value): raise ValueError('non-finite native access setting')
            return value
        if abs(number('FixedStepSampling')-step)>1e-9:
            raise ValueError('native regional fixed step differs')
        if number('TimeConvergence')>.01000001:
            raise ValueError('native event tolerance exceeds 0.01 seconds')
        if not re.search(r'^\s*UseLightTimeDelay\s+No\s*$',block,re.M):
            raise ValueError('native access still enables light time')
    if found!=expected: raise ValueError('native saved access pairs are incomplete')
    return dict(pairs=len(found),fixed_step_s=step,verified=True)


def native_global_sampling(path, settings):
    text=Path(path).read_text(encoding='utf-8-sig')
    m=re.search(r'BEGIN AccessDefinition(.*?)END AccessDefinition',text,re.S)
    if not m: raise ValueError('native coverage access settings missing')
    values=dict(re.findall(r'^\s*(\w+)\s+(\S+)\s*$',m[1],re.M))
    for key in ['Convergence','MaxTimeStep','MinTimeStep','FixedStepSampling']:
        if key in values and not math.isfinite(float(values[key])):
            raise ValueError('non-finite native coverage setting')
    if values.get('UseLightTimeDelay')!='No' or values.get('DetectEventsUsingSamplesOnly')!='No':
        raise ValueError('native coverage event settings differ')
    if float(values['Convergence'])>.01000001: raise ValueError('native coverage tolerance differs')
    if settings['global_sampling']=='adaptive':
        if 'FixedStepSampling' in values: raise ValueError('native coverage is not adaptive')
        if abs(float(values['MaxTimeStep'])-settings['global_max_step_s'])>1e-9 or abs(float(values['MinTimeStep'])-.001)>1e-9:
            raise ValueError('native adaptive limits differ')
    elif abs(float(values.get('FixedStepSampling','nan'))-settings['global_step_s'])>1e-9 or 'FixedStepSampling' not in values:
        raise ValueError('native global fixed step differs')
    return dict(verified=True,settings=values)
