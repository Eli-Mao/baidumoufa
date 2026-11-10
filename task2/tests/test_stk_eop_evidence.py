from pathlib import Path
import tempfile
import unittest
from stk_evidence import native_eop_binding


class EarthOrientationEvidence(unittest.TestCase):
    def setup_files(self,directory):
        base=Path(directory);run=base/'run';package=base/'package'
        run.mkdir();package.mkdir()
        name='frozen.txt'
        data='VERSION 1.1\nUPDATED 2026 Nov 04\n'+'\n'.join(f'2027 01 {d:02d} 0' for d in range(1,9))
        for root in [run,package]:(root/name).write_text(data)
        (run/'Task2_Constellation.sc').write_text('EOPFilename frozen.txt\n')
        manifest=dict(eop_file=name,eop_provenance=dict(scenario_dates_are_predictions=True))
        return run,package,manifest

    def test_snapshot_and_scenario_dates_are_verified(self):
        with tempfile.TemporaryDirectory() as d:
            run,package,manifest=self.setup_files(d)
            self.assertTrue(native_eop_binding(run,package,manifest)['frozen'])
            for root in [run,package]:
                p=root/'frozen.txt';p.write_text(p.read_text().replace('2027 01 08 0',''))
            with self.assertRaises(ValueError):native_eop_binding(run,package,manifest)

    def test_different_file_or_modified_snapshot_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            run,package,manifest=self.setup_files(d)
            (run/'Task2_Constellation.sc').write_text('EOPFilename old.txt\n')
            with self.assertRaises(ValueError):native_eop_binding(run,package,manifest)
            (run/'Task2_Constellation.sc').write_text('EOPFilename frozen.txt\n')
            (run/'frozen.txt').write_text('different data')
            with self.assertRaises(ValueError):native_eop_binding(run,package,manifest)


if __name__=='__main__':unittest.main()
