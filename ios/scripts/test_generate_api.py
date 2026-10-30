"""Compatibility input tests: canonical schemas stay unchanged and closed."""
import copy
import json
from pathlib import Path
import unittest
from generate_api import generator_input,NULL_NAME


class GeneratorInputTests(unittest.TestCase):
    def test_nullable_marker_becomes_strict_codec_reference(self):
        source={'components':{'schemas':{'Status':{'type':'object','additionalProperties':False,
            'required':['value'],'properties':{'value':{'oneOf':[{'type':'integer'},{'type':'null'}]}}}}}}
        before=copy.deepcopy(source)
        result,paths=generator_input(source)
        self.assertEqual(source,before)
        status=result['components']['schemas']['Status']
        self.assertFalse(status['additionalProperties']);self.assertEqual(status['required'],['value'])
        self.assertEqual(status['properties']['value']['oneOf'][0],{'type':'integer'})
        self.assertEqual(status['properties']['value']['oneOf'][1],{'$ref':'#/components/schemas/'+NULL_NAME})
        self.assertEqual(len(paths),1)

    def test_unknown_null_constraints_or_name_collision_refuse_generation(self):
        for schemas in [{'Field':{'type':'null','unexpected':True}},{NULL_NAME:{}}]:
            with self.assertRaises(ValueError):generator_input({'components':{'schemas':schemas}})

    def test_real_status_and_reference_fields_remain_required(self):
        path=Path(__file__).resolve().parents[2]/'contracts/api/openapi.json';raw=path.read_bytes()
        source=json.loads(raw);result,paths=generator_input(source)
        for name,fields in [('MessageSendStatusV2Response',['receipt','head','reference']),
                            ('MessageTravelReferenceNone',['context_id','context_version'])]:
            for field in fields:self.assertIn(field,result['components']['schemas'][name]['required'])
        self.assertTrue(paths);self.assertEqual(path.read_bytes(),raw)

if __name__=='__main__':unittest.main()
