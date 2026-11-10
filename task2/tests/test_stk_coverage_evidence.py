from pathlib import Path
import tempfile
import unittest
import numpy as np
from summarize_stk_coverage import parse_cvaa,summarize

EXAMPLE='''COV 6.0
EpochTime 1 Jan 2027 00:00:00.000000
NumberOfAssets 1
0 Satellite/SAT_001/Sensor/Cam
NumberOfRegions 1
RegionNumber 0
NumPtsInRegion 2
PointNumber 0
Lat 0
Lon 3.141592653589793
Alt 0
NumberOfAccesses 2
0 10 20
0 50 60
PointNumber 1
Lat 0
Lon 0
Alt 0
NumberOfAccesses 0
'''


class StkCoverageEvidence(unittest.TestCase):
    def parse(self,text):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'sample.txt';p.write_text(text)
            return parse_cvaa(p,[1],100)

    def test_radians_longitude_wrap_and_uncovered_points(self):
        points,meta=self.parse(EXAMPLE)
        self.assertEqual(meta['access_rows'],2)
        result=summarize(points,np.array([[0,-180,0],[0,0,0]]))
        self.assertEqual(result['coverage'],.5)
        self.assertIsNone(result['T90_s'])
        self.assertIsNone(result['T100_s'])
        self.assertEqual(points.first_access_s.iloc[0],10)

    def test_truncated_rows_and_wrong_grid_fail(self):
        with self.assertRaises(ValueError): self.parse(EXAMPLE.replace('NumberOfAccesses 2','NumberOfAccesses 3'))
        points,_=self.parse(EXAMPLE)
        with self.assertRaises(ValueError): summarize(points,np.array([[0,-180,0],[1,0,0]]))

    def test_unknown_asset_and_out_of_range_interval_fail(self):
        with self.assertRaises(ValueError): self.parse(EXAMPLE.replace('0 10 20','1 10 20'))
        with self.assertRaises(ValueError): self.parse(EXAMPLE.replace('0 10 20','0 10 101'))

    def test_native_repeated_region_label_preserves_distinct_points(self):
        native=EXAMPLE.replace('NumberOfRegions 1','NumberOfRegions 2').replace(
            'NumPtsInRegion 2','NumPtsInRegion 1').replace(
            'PointNumber 1','RegionNumber 0\nNumPtsInRegion 1\nPointNumber 1')
        points,_=self.parse(native)
        self.assertEqual(points.region_id.tolist(),[0,0])
        self.assertEqual(points.region_index.tolist(),[0,1])
        with self.assertRaises(ValueError): self.parse(native.replace('PointNumber 1','PointNumber 0'))


if __name__=='__main__':unittest.main()
