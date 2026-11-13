"""Compatibility input tests: canonical schemas stay unchanged and closed."""
import copy
import json
from pathlib import Path
import unittest
from generate_api import generator_input,NULL_NAME,concrete_null_constructors


class GeneratorInputTests(unittest.TestCase):
    def test_required_nullable_anyof_uses_concrete_codec_without_changing_shape(self):
        source='''public struct titlePayload: Codable {
    public var value1: Swift.String?
    public var value2: Components.Schemas.CJExplicitJSONNull?
    public init(from decoder: any Swift.Decoder) throws {
        self.value1 = try decoder.decodeFromSingleValueContainer()
        self.value2 = try .init(from: decoder)
        try Swift.DecodingError.verifyAtLeastOneSchemaIsNotNil([])
    }
}'''
        result,count=concrete_null_constructors(source)
        self.assertEqual(count,1)
        self.assertEqual(result,source.replace('self.value2 = try .init(from: decoder)',
            'self.value2 = try Components.Schemas.CJExplicitJSONNull(from: decoder)'))
        self.assertEqual(concrete_null_constructors(result),(result,0))

    def test_oneof_and_unknown_generated_shapes_are_not_rewritten(self):
        oneof='case CJExplicitJSONNull(Components.Schemas.CJExplicitJSONNull)'
        self.assertEqual(concrete_null_constructors(oneof),(oneof,0))
        with self.assertRaises(ValueError):
            concrete_null_constructors('public var value2: Components.Schemas.CJExplicitJSONNull?')
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
