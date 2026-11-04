import sys,unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from reconcile_v5_audit import endpoint_membership

class TestEndpointMembership(unittest.TestCase):
    def test_endpoint_present_even_when_arange_has_an_extra_nearby_value(self):
        d=float(np.nextafter(240.,0.))
        present,n,excess=endpoint_membership(d)
        self.assertTrue(present);self.assertEqual(n,242);self.assertGreater(excess,0.)
        self.assertLess(excess,1e-9)

if __name__=='__main__':unittest.main()
