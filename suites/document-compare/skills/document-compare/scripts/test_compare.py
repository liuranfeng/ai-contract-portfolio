import copy
import unittest
from input_adapter import import_document, reading_text
from alignment import align_documents, character_ops
from semantics import apply_decisions, semantic_requests
from compare import validate_result

def doc(texts,index=0,ids=None):
    raw={'parse_run_id':'fixture','pages':[{'page_num':0,'layouts':[{'layout_id':(ids or list(range(len(texts))))[i],'text':t} for i,t in enumerate(texts)]}]}
    return import_document(raw,index,'模拟文件')

class ComparisonTests(unittest.TestCase):
    def compare(self,a,b,mode='character',**kw):
        return align_documents(doc(a),doc(b,1),mode=mode,**kw)

    def test_native_ids_not_sort_keys(self):
        a=doc(['甲','乙'],ids=['90','2'])
        self.assertEqual([x['layoutId'] for x in a['layouts']],['90','2'])
        self.assertEqual([x['ordinal'] for x in a['layouts']],[0,1])

    def test_id_type_and_duplicates(self):
        self.assertEqual(len(doc(['甲','乙'],ids=[1,'1'])['layouts']),2)
        with self.assertRaises(ValueError):doc(['甲','乙'],ids=[1,1])
        with self.assertRaises(ValueError):import_document({'pages':[{'layouts':[{'text':'甲'}]}]},0,'x')

    def test_explicit_reading_order(self):
        d=import_document({'pages':[{'layouts':[{'layout_id':'a','text':'后','reading_order':2},{'layout_id':'b','text':'前','reading_order':1}]}]},0,'x')
        self.assertEqual([x['text'] for x in d['layouts']],['前','后'])

    def test_table_text_and_plain_whitespace(self):
        self.assertEqual(reading_text(' a  b\r\nC '),' a  b\r\nC ')
        self.assertEqual(reading_text('<table><tr><td>甲</td><td>3年</td></tr><tr><td>乙</td><td>5年</td></tr></table>'),'甲\t3年\n乙\t5年')
        self.assertEqual(reading_text('| 项目 | 数值 |\n|---|---|\n|质保|3年|'),'项目\t数值\n质保\t3年')

    def test_insert_does_not_shift_following(self):
        r=self.compare(['服务约定','验收标准','支付方式'],['服务约定','新增培训','验收标准','支付方式'])
        self.assertEqual([x['operation'] for x in r['alignments']],['equal','insert','equal','equal'])

    def test_delete_direction(self):
        r=self.compare(['甲','待删','乙'],['甲','乙'])
        x=r['alignments'][1];self.assertEqual(x['operation'],'delete');self.assertEqual(x['right'],[])

    def test_repeated_paragraphs_covered(self):
        r=self.compare(['通用','甲','通用','乙'],['通用','甲','新','通用','乙'])
        self.assertEqual([i for x in r['alignments'] for i in x['left']],list(range(4)))
        self.assertEqual([i for x in r['alignments'] for i in x['right']],list(range(5)))

    def test_split_layout_can_align(self):
        r=self.compare(['第一段完整文字。第二段完整文字。'],['第一段完整文字。','第二段完整文字。'])
        self.assertEqual(len(r['alignments']),1)
        self.assertEqual(r['alignments'][0]['right'],[0,1])

    def test_character_is_strict(self):
        for right in ['a b。','Ab。','ab','ab。 ','ab。\n']:
            with self.subTest(right=right):self.assertNotEqual(self.compare(['ab。'],[right])['alignments'][0]['operation'],'equal')

    def test_unicode_roundtrip(self):
        a='设备😀质保3年。';b='设备😀免费质保5年。'
        ops=character_ops(a,b)
        self.assertEqual(''.join(b[x['rightStart']:x['rightEnd']] for x in ops),b)
        self.assertEqual(''.join(a[x['leftStart']:x['leftEnd']] for x in ops),a)

    def test_semantics_never_guessed(self):
        r=self.compare(['每月支付一次费用'],['费用按月支付'],mode='semantic')
        self.assertEqual(r['status'],'needs_review')
        self.assertTrue(all(x['semantic']['status']=='pending' for x in r['alignments']))
        self.assertTrue(semantic_requests(r)['requests'])

    def test_semantic_decision_bound_to_evidence(self):
        r=self.compare(['免费质保3年'],['免费质保5年'],mode='semantic')
        a=r['alignments'][0]
        decisions={'comparisonId':r['comparisonId'],'decisions':[{'id':a['id'],'status':'changed','reason':'期限从3年增加为5年','leftQuote':'3年','rightQuote':'5年'}]}
        applied=apply_decisions(r,decisions)
        self.assertEqual(applied['status'],'complete')
        self.assertEqual(r['alignments'][0]['semantic']['status'],'pending')
        bad=copy.deepcopy(decisions);bad['decisions'][0]['rightQuote']='10年'
        with self.assertRaises(ValueError):apply_decisions(r,bad)
        bad=copy.deepcopy(decisions);bad['comparisonId']='wrong'
        with self.assertRaises(ValueError):apply_decisions(r,bad)

    def test_long_documents_exact_anchors(self):
        a=[f'第{i}项承诺按约定执行' for i in range(2200)];b=a[:1100]+['额外培训']+a[1100:]
        r=self.compare(a,b)
        self.assertEqual(r['summary']['insert'],1)
        self.assertEqual(r['coverage'],{'left':2200,'right':2201})

    def test_move_stays_reading_order(self):
        r=self.compare(['条款甲','条款乙','条款丙'],['条款丙','条款甲','条款乙'])
        self.assertEqual([i for x in r['alignments'] for i in x['left']],list(range(3)))
        self.assertEqual([i for x in r['alignments'] for i in x['right']],list(range(3)))

    def test_tampered_result_rejected(self):
        r=self.compare(['3年'],['5年']);validate_result(r)
        r['alignments'][0]['rightText']='10年'
        with self.assertRaises(ValueError):validate_result(r)

    def test_unanchored_long_gap_is_not_silently_matched(self):
        r=self.compare(['甲']*20,['乙']*25,max_cells=100)
        self.assertEqual(r['status'],'needs_review')
        self.assertEqual(r['coverage'],{'left':20,'right':25})
        self.assertEqual(r['alignments'][0]['alignmentStatus'],'unresolved')

    def test_large_character_ranges_preserve_every_character(self):
        a='甲乙丙丁'*12000;b=a[:18001]+'变更'+a[18001:]
        ops=character_ops(a,b)
        self.assertEqual(''.join(a[x['leftStart']:x['leftEnd']] for x in ops),a)
        self.assertEqual(''.join(b[x['rightStart']:x['rightEnd']] for x in ops),b)

    def test_manual_alignment_must_cover_in_order(self):
        with self.assertRaises(ValueError):self.compare(['甲','乙'],['一','二'],alignment_override=[{'left':[1,0],'right':[0,1]}])

    def test_images_are_not_certified_by_equal_text(self):
        a=import_document({'pages':[{'layouts':[{'layout_id':0,'type':'image','text':''}]}]},0,'左图')
        b=copy.deepcopy(a);b['documentIndex']=1
        self.assertEqual(align_documents(a,b)['status'],'needs_review')

    def test_legacy_generated_ids_rejected(self):
        raw={'parser':'baidu-document-parser/paddle-vl','pages':[{'layouts':[{'layout_id':'lay-p1-i0','text':'正文'}]}]}
        with self.assertRaises(ValueError):import_document(raw,0,'旧适配结果')

    def test_document_index_and_order_types(self):
        raw={'pages':[{'layouts':[{'layout_id':1,'text':'正文','reading_order':float('nan')}]}]}
        with self.assertRaises(ValueError):import_document(raw,0,'x')
        with self.assertRaises(ValueError):import_document({'pages':[{'layouts':[{'layout_id':1,'text':'x'}]}]},True,'x')

if __name__=='__main__':unittest.main()
