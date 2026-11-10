import hashlib
from pathlib import Path
import tempfile
import unittest

from summarize_stk_region import check_package_binding


class PackageBindingTests(unittest.TestCase):
    def test_wrong_constellation_with_identical_ids_is_rejected(self):
        names=['manifest.json','build_scenario.txt','build_coverage.txt',
               'GlobalAll.pnt','GlobalReachable.pnt','YRD_GridDiagnostic.pnt']
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            evidence={}
            for name in names:
                (root/name).write_bytes(b'{}' if name=='manifest.json' else name.encode())
                evidence[name]=hashlib.sha256((root/name).read_bytes()).hexdigest()
            self.assertTrue(check_package_binding(root,evidence))
            (root/'build_scenario.txt').write_bytes(b'different orbital phase')
            with self.assertRaisesRegex(ValueError,'different or modified'):
                check_package_binding(root,evidence)

    def test_missing_evidence_cannot_pass(self):
        with self.assertRaises(ValueError):
            check_package_binding('.',{})


if __name__=='__main__': unittest.main()
