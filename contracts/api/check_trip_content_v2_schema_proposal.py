"""Pure structural proposal checks; no producer, API, generator or provider execution."""
import copy
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import subprocess
import sys
import unittest
from jsonschema import Draft202012Validator,FormatChecker

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
BASE='a10ad8998fbac4e2a648dd0137f1872eb12b8239'
SCHEMA=HERE/'trip-content-v2-schema-proposal.json'
EXAMPLES=HERE/'trip-content-v2-schema-examples.json'

def materialize(fixtures,case):
    """Apply local fixture replacements only; this is not a product patch interface."""
    value=copy.deepcopy(fixtures['base'])
    for change in case['changes']:
        path=change['path']
        if not path:value=copy.deepcopy(change['value']);continue
        parent=value
        for part in path[:-1]:parent=parent[part]
        if change.get('delete'):del parent[path[-1]]
        else:parent[path[-1]]=copy.deepcopy(change['value'])
    return value

class ProposalChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema=json.loads(SCHEMA.read_text());cls.fixtures=json.loads(EXAMPLES.read_text())
        cls.validator=Draft202012Validator(cls.schema,format_checker=FormatChecker())
    def test_local_refs_and_valid_metaschema(self):
        Draft202012Validator.check_schema(self.schema)
        def visit(value):
            if isinstance(value,dict):
                if '$ref' in value:self.assertTrue(value['$ref'].startswith('#/$defs/'))
                for item in value.values():visit(item)
            elif isinstance(value,list):
                for item in value:visit(item)
        visit(self.schema)
        self.assertEqual(self.schema['x-cj-status'],'UNREGISTERED_PRODUCER_ABI_FIXED_WIRE_NOT_ACCEPTED')
    def test_structural_positive_examples_do_not_mutate_input(self):
        for case in self.fixtures['schema_accept']:
            with self.subTest(case=case['name']):
                value=materialize(self.fixtures,case);before=copy.deepcopy(value)
                self.validator.validate(value);self.assertEqual(value,before)
    def test_structural_negative_examples(self):
        for case in self.fixtures['schema_reject']:
            with self.subTest(case=case['name']):
                self.assertTrue(list(self.validator.iter_errors(materialize(self.fixtures,case))))
    def test_producer_and_application_gates_are_not_schema_success_claims(self):
        for group in ['producer_gate_only','application_gate_only']:
            for case in self.fixtures[group]:
                with self.subTest(group=group,case=case['name']):
                    self.assertTrue(case['reason']);self.validator.validate(materialize(self.fixtures,case))
        # Standard JSON Schema integer permits integral floats; original producer
        # token-type validation is intentionally not replaced by a custom dialect.
        self.assertTrue(self.validator.is_valid({**self.fixtures['base'],'content_version':2.0}))
    def test_six_place_absence_states_without_present_or_value_escape(self):
        place=self.schema['$defs']['PlaceAbsence']
        self.assertEqual(place['properties']['state']['enum'],['missing','empty_array','empty_string','null','invalid','unknown'])
        self.assertIs(place['additionalProperties'],False)
        self.assertEqual(set(place['properties']),{'state'})
    def test_original_v1_and_generator_registration_unchanged(self):
        frozen=['contracts/api/openapi.json','scripts/generate.sh']
        original=subprocess.check_output(['git','-C',str(ROOT),'show',BASE+':'+frozen[1]])
        self.assertEqual((ROOT/frozen[1]).read_bytes(),original,frozen[1])
        # Existing V1 schemas stay byte-for-byte equivalent. P2c adds only the
        # confirmation envelopes; this still forbids registering the V2 proposal.
        formal=json.loads((ROOT/frozen[0]).read_text())
        base=json.loads(subprocess.check_output(['git','-C',str(ROOT),'show',BASE+':'+frozen[0]]))
        trip=lambda spec:{k:v for k,v in spec['components']['schemas'].items() if k.startswith('Trip')}
        original_trip=trip(base);current_trip=trip(formal)
        self.assertEqual(set(current_trip)-set(original_trip),
                         {'TripConfirmationRequest','TripConfirmationResponse'})
        self.assertEqual({name:current_trip[name] for name in original_trip},original_trip)
        v1=Draft202012Validator({'$ref':'#/components/schemas/TripDocument','components':formal['components']})
        v1.validate(self.fixtures['v1_original'])
        self.assertFalse(v1.is_valid(self.fixtures['base']))
        with_version={**self.fixtures['v1_original'],'content_version':1}
        self.assertFalse(v1.is_valid(with_version))
        self.assertNotIn('TripDocumentV2',formal['components']['schemas'])
        self.assertNotIn(SCHEMA.name,(ROOT/frozen[0]).read_text())
        script=(ROOT/frozen[1]).read_text()
        self.assertIn('--input contracts/api/openapi.json',script);self.assertNotIn(SCHEMA.name,script)
        self.assertFalse(self.validator.is_valid(self.fixtures['v1_original']))

if __name__=='__main__':
    print('base='+BASE+'; trip grammar7e6; public ABI7262c749fd0b81e3ff5e8ed9f3275169c49c1598; FORMAL_WIRE_NOT_ACCEPTED',flush=True)
    print('Python='+sys.version.split()[0]+'; jsonschema='+version('jsonschema')+'; Draft2020-12 with date FormatChecker; no producer/runtime imports',flush=True)
    for path in [SCHEMA,EXAMPLES]:print(path.name+' SHA256='+hashlib.sha256(path.read_bytes()).hexdigest(),flush=True)
    result=unittest.TextTestRunner(stream=sys.stdout,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ProposalChecks))
    f=json.loads(EXAMPLES.read_text());print('case counts: '+json.dumps({g:len(f[g]) for g in ['schema_accept','schema_reject','producer_gate_only','application_gate_only']}),flush=True)
    raise SystemExit(0 if result.wasSuccessful() else 1)
