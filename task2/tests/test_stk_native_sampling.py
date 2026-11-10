from pathlib import Path
import tempfile
import unittest
from stk_evidence import native_region_sampling,native_global_sampling


class NativeSamplingEvidence(unittest.TestCase):
    def test_com_claim_cannot_replace_saved_fixed_step(self):
        text='''BEGIN Access
Scenario/Test/Satellite/SAT_001/Sensor/Cam
Scenario/Test/AreaTarget/YRD_000
UseLightTimeDelay No
TimeConvergence 0.01
FixedStepSampling 0.125
END Access
'''
        manifest=dict(satellite_ids=[1],region_area_targets=['YRD_000'])
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'saved.sca';p.write_text(text)
            self.assertTrue(native_region_sampling(p,manifest,.125)['verified'])
            with self.assertRaises(ValueError):native_region_sampling(p,manifest,.0625)
            p.write_text(text.replace('FixedStepSampling 0.125\n',''))
            with self.assertRaises(ValueError):native_region_sampling(p,manifest,.125)
            p.write_text(text.replace('FixedStepSampling 0.125','FixedStepSampling nan'))
            with self.assertRaises(ValueError):native_region_sampling(p,manifest,.125)

    def test_global_adaptive_requires_native_limits(self):
        text='''BEGIN AccessDefinition
UseLightTimeDelay No
DetectEventsUsingSamplesOnly No
Convergence 0.01
MinTimeStep 0.001
MaxTimeStep 60
END AccessDefinition
'''
        settings=dict(global_sampling='adaptive',global_max_step_s=60)
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'saved.cv';p.write_text(text)
            self.assertTrue(native_global_sampling(p,settings)['verified'])
            p.write_text(text.replace('MaxTimeStep 60','MaxTimeStep 360'))
            with self.assertRaises(ValueError):native_global_sampling(p,settings)
            p.write_text(text.replace('MaxTimeStep 60','MaxTimeStep nan'))
            with self.assertRaises(ValueError):native_global_sampling(p,settings)


if __name__=='__main__':unittest.main()
