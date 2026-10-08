import copy
import json
from pathlib import Path
import unittest
from review_run import append_review

class ReviewRunTests(unittest.TestCase):
    def setUp(self):
        self.data=json.loads((Path(__file__).parents[1]/'examples/demo.json').read_text(encoding='utf-8'))
        self.check=copy.deepcopy(self.data['checks'][0]); self.check['checkId']='NEW-1'
        self.check['priorCheckIds']=[self.data['checks'][0]['checkId']]
        self.patch={'snapshotId':'new-snapshot','scope':'Only the explicitly cited sources were reread.','facts':[], 'checks':[self.check]}
    def test_preserves_history_and_coverage_and_records_bridge(self):
        before=copy.deepcopy(self.data)
        data,bridge=append_review(self.data,self.patch)
        self.assertEqual(self.data,before)
        self.assertEqual(data['checks'][1:],before['checks'])
        self.assertEqual(data['coverage'],before['coverage'])
        self.assertEqual(data['reportView']['mainCheckIds'],['NEW-1'])
        self.assertIn('NEW-1',bridge[0]['reviewCheckIds'])
    def test_rejects_reused_id_unknown_history_and_same_snapshot(self):
        for change in ('id','prior','snapshot'):
            p=copy.deepcopy(self.patch)
            if change=='id':p['checks'][0]['checkId']=self.data['checks'][0]['checkId']
            if change=='prior':p['checks'][0]['priorCheckIds']=['DOES-NOT-EXIST']
            if change=='snapshot':p['snapshotId']=self.data['snapshotId']
            with self.assertRaises(ValueError):append_review(self.data,p)

if __name__=='__main__':unittest.main()
