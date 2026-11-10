"""Independent native fixtures and regression cases for the repaired workflow."""
import contextlib
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
import designs
from constellation import epoch_jd
from model_convention import element_model,using_rate_model,rate_model
from generate import output_table
from evaluate import legal,main as evaluate_main
from validate import check_output
from earth_frames import EarthFrames,StkOrbit,geodetic_xyz,AXES
from ellipsoid_coverage import satellite_intervals
from compare_geometry import points_comparison,windows_comparison,read_refinement
from run_sim import load_elements

DATA=Path(__file__).parent/'data'
ROOT=DATA.parents[1]


class ConventionIntegration(unittest.TestCase):
    def test_new_and_legacy_designs_are_identified_and_validated(self):
        fresh=designs.walker(4,4,1,700.)
        self.assertEqual(element_model(fresh),'stk')
        self.assertTrue(legal(fresh,4)[0])
        self.assertTrue(check_output(output_table(fresh).rename(columns={'h_km':'alt_km'}))['ok'])
        with using_rate_model('first_order'):
            legacy=designs.walker(4,4,1,700.)
        self.assertEqual(element_model(legacy),'first_order')
        self.assertTrue(legal(legacy,4)[0])
        self.assertFalse(legal(legacy,4,'stk')[0])
        mixed=pd.concat([legacy.iloc[:1],fresh.iloc[1:]],ignore_index=True)
        with self.assertRaises(ValueError):element_model(mixed)
        self.assertEqual(rate_model(),'stk')

    def test_scoped_convention_restores_after_exception(self):
        with self.assertRaises(RuntimeError):
            with using_rate_model('first_order'):
                self.assertEqual(rate_model(),'first_order')
                raise RuntimeError('stop')
        self.assertEqual(rate_model(),'stk')

    def test_old_references_cannot_score_new_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            d=Path(directory);output_table(designs.walker(4,4,1,700.)).to_csv(d/'input.csv',index=False)
            (d/'refs.json').write_text(json.dumps({'refs':{'T90_d':1,'T100_d':1,'Tavg_h':1,'Tmax_h':1}}))
            with contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit) as cm:
                evaluate_main(['--elements',str(d/'input.csv'),'--refs',str(d/'refs.json')])
            self.assertEqual(cm.exception.code,2)

    def test_native_sso_at_three_heights_four_planes(self):
        native=json.loads((DATA/'stk116_sso_multiplane_reference.json').read_text(encoding='utf-8-sig'))
        self.assertEqual(len(native['satellites']),12)
        self.assertLess(native['max_error_deg_day'],1e-6)
        from sso import design_inclination
        frames=EarthFrames()
        from types import SimpleNamespace
        for row in native['satellites']:
            expected=design_inclination(row['height_km'],row['raan_j2000_deg'])
            self.assertLess(abs(expected-row['inclination_j2000_deg']),5.001e-7)
            el=SimpleNamespace(alt_km=row['height_km'],inc_deg=row['inclination_j2000_deg'],
                               raan_deg=row['raan_j2000_deg'],u_deg=0.)
            predicted=np.degrees(StkOrbit(el,frames).rd)*86400
            self.assertAlmostEqual(predicted,row['measured_node_rate_deg_day'],delta=1e-8)


class NativeGeometryRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frames=EarthFrames()
        cls.elements=load_elements(ROOT/'tests/data/stk116_alignment_elements.csv').set_index('sat_id')

    def test_native_fixed_positions_and_attitude_velocities(self):
        samples=pd.read_csv(DATA/'stk116_fixed_reference.csv')
        for sid,rows in samples[samples.frame=='Fixed'].groupby('sat_id'):
            r,v=StkOrbit(self.elements.loc[sid],self.frames).state(rows.t_s.to_numpy())
            self.assertLess(np.linalg.norm(r-rows[['x_km','y_km','z_km']].to_numpy(),axis=1).max(),.000002)
            self.assertLess(np.linalg.norm(v-rows[['vx_kms','vy_kms','vz_kms']].to_numpy(),axis=1).max(),.000001)

    def test_ellipsoid_surface_normals_and_height(self):
        p=geodetic_xyz([0,40,-160],[0,45,89])
        np.testing.assert_allclose(np.sum((p/AXES)**2,axis=1),1,atol=1e-14)
        normal=p/AXES**2
        lat=np.degrees(np.arctan2(normal[:,2],np.hypot(normal[:,0],normal[:,1])))
        np.testing.assert_allclose(lat,[0,45,89],atol=1e-12)
        self.assertAlmostEqual(np.linalg.norm(geodetic_xyz(0,0,1)-geodetic_xyz(0,0)),1.)

    def test_native_grazing_gap_is_preserved_and_candidate_spacing_converges(self):
        expected=pd.read_csv(DATA/'stk116_grazing_reference.csv')
        point=geodetic_xyz(expected.lon_deg.iloc[:1].to_numpy(),expected.lat_deg.iloc[:1].to_numpy())
        orbit=StkOrbit(self.elements.loc[25],self.frames)
        results=[]
        for step in (10.,5.):
            windows=satellite_intervals(orbit,point,cKDTree(point),35121.,step)
            windows=windows[np.argsort(windows[:,1])]
            self.assertEqual(len(windows),2)
            self.assertGreater(windows[1,1]-windows[0,2],2.)
            np.testing.assert_allclose(windows[:,1:],expected[['start_s','stop_s']],atol=.001,rtol=0)
            results.append(windows)
        np.testing.assert_allclose(*results,atol=.001,rtol=0)

    def test_missing_eop_dates_fail_instead_of_extrapolating(self):
        with self.assertRaises(ValueError):EarthFrames(epoch_jd(2030),604800.)
        with self.assertRaises(ValueError):self.frames.matrix(np.array([np.nan]))


class CompleteEvidenceRegression(unittest.TestCase):
    def test_duplicate_or_missing_grid_coordinates_are_rejected(self):
        a=pd.DataFrame(dict(lat_deg=[0.,1.],lon_deg=[0.,0.],n_accesses=[1,0],first_access_s=[1.,np.nan]))
        self.assertTrue(points_comparison(a,a)['ok'])
        with self.assertRaises(ValueError):points_comparison(a,a.iloc[:1])
        with self.assertRaises(ValueError):points_comparison(a,pd.concat([a.iloc[:1],a.iloc[:1]]))
        bad=a.copy();bad.loc[1,'first_access_s']=3
        with self.assertRaises(ValueError):points_comparison(a,bad)

    def test_missing_visit_or_satellite_mismatch_cannot_pass(self):
        a=pd.DataFrame(dict(sat_id=[1,1],start_s=[1.,3.],stop_s=[2.,4.]))
        self.assertFalse(windows_comparison(a,a.iloc[:1])['ok'])
        b=a.copy();b.loc[1,'sat_id']=2
        self.assertFalse(windows_comparison(a,b)['ok'])

    def test_native_refinement_sampling_and_period_are_bound(self):
        cases,windows,status=read_refinement(DATA/'grazing_native')
        self.assertEqual((len(cases),len(windows)),(1,2))
        with tempfile.TemporaryDirectory() as directory:
            copy=Path(directory)/'native';shutil.copytree(DATA/'grazing_native',copy)
            f=copy/'Task2_Constellation.sca'
            f.write_text(f.read_text().replace('FixedStepSampling\t\t 0.002','FixedStepSampling\t\t 0.2'))
            with self.assertRaises(ValueError):read_refinement(copy)


if __name__=='__main__':unittest.main()
