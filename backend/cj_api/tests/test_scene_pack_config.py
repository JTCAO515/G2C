"""Scene packs and switches (#1737, ADR-0010): format, defaults, travel unchanged with business off."""
import json
from pathlib import Path
import re
import shutil
import tempfile
import unittest

from cj_api import scene_pack_config as config

ROOT=Path(__file__).resolve().parents[3]
REGISTRY=ROOT/'ios/Modules/CJShell/Sources/CJLioUser/LioToolRegistry.swift'
# #1980: hub and merged-card ids that exist only on the Tools tab. The server never names them (a scene pack
# lists KNOWN_TOOLS only, and answer buttons come from the fixed table), so they are not in KNOWN_TOOLS.
APP_ONLY_TOOLS=frozenset({'eat-play','convenience','money'})


class ScenePackTests(unittest.TestCase):
    def setUp(self):
        self.directory=Path(tempfile.mkdtemp());self.addCleanup(shutil.rmtree,self.directory)
        for path in config.DIRECTORY.glob('*.json'):shutil.copy(path,self.directory/path.name)

    def edit(self,name,change):
        path=self.directory/name;data=json.loads(path.read_text());change(data);path.write_text(json.dumps(data))

    def test_shipped_packs_and_switches_load(self):
        travel,business=(config.load_pack(name) for name in config.PACKS)
        self.assertEqual((travel.cities,business.cities),((),('guangzhou',)))
        self.assertEqual(set(travel.tools),config.KNOWN_TOOLS)
        self.assertLessEqual(set(business.tools),config.KNOWN_TOOLS)

    def test_everything_new_starts_off_and_travel_stays_on(self):
        switches=config.load_switches()
        self.assertEqual(switches.scene_packs,{'travel':True,'business':False})
        self.assertEqual(switches.cities,{'business':{'guangzhou':False}})
        self.assertFalse(switches.human_service or switches.payments or switches.medical)

    def test_business_off_leaves_only_travel_active(self):
        self.assertEqual([pack.name for pack in config.active_packs()],['travel'])
        business=config.load_pack('business')
        self.assertFalse(config.city_enabled(business,'guangzhou'))
        self.assertTrue(config.city_enabled(config.load_pack('travel'),'beijing'))

    def test_business_needs_both_pack_and_city_switch(self):
        self.edit('switches.json',lambda d:d['scene_packs'].update(business=True))
        business=config.load_pack('business',self.directory);switches=config.load_switches(self.directory)
        self.assertEqual([p.name for p in config.active_packs(switches,self.directory)],['travel','business'])
        self.assertFalse(config.city_enabled(business,'guangzhou',switches,self.directory))
        self.edit('switches.json',lambda d:d['cities']['business'].update(guangzhou=True))
        switches=config.load_switches(self.directory)
        self.assertTrue(config.city_enabled(business,'guangzhou',switches,self.directory))
        self.assertFalse(config.city_enabled(business,'beijing',switches,self.directory))

    def test_only_listed_runtime_modules_read_packs_so_build57_behaviour_is_unchanged(self):
        # Each ticket that reads packs adds its own module here; any other reader still fails this test.
        allowed=['backend/cj_api/lio_fact_blocks.py',  # #1859 business facts, behind CJ_LIO_FACT_BLOCKS (default off)
                 'backend/cj_api/lio_tasks.py']  # W2-8 #1738 task understanding, behind CJ_LIO_TASKS (default off)
        readers=sorted(str(path.relative_to(ROOT)) for base in ('backend','deploy','scripts') for path in (ROOT/base).rglob('*.py')
                       if 'tests' not in path.parts and path.name!='scene_pack_config.py'
                       and re.search(r'\bscene_pack_config\b',path.read_text(errors='ignore')))
        self.assertEqual(readers,allowed)

    def test_tool_ids_match_the_app_registry(self):
        registry=set(re.findall(r'LioTool\("([a-z-]+)"\)',REGISTRY.read_text()))
        self.assertTrue(APP_ONLY_TOOLS<=registry,'an App-only id must stay in the registry or leave this list')
        self.assertTrue(APP_ONLY_TOOLS.isdisjoint(config.KNOWN_TOOLS))
        self.assertEqual(registry-APP_ONLY_TOOLS,config.KNOWN_TOOLS)

    def test_format_fails_closed(self):
        cases=[
            ('business.json',lambda d:d['tools'].append('book-factory-visit'),'scene_pack_tools_invalid'),
            ('business.json',lambda d:d.update(cities=['lhasa']),'scene_pack_cities_invalid'),
            ('business.json',lambda d:d['risk_rules'][0]['rule'].pop('zh'),'scene_pack_risk_rules_invalid'),
            ('business.json',lambda d:d.update(risk_rules=[]),'scene_pack_risk_rules_required'),
            ('business.json',lambda d:d.update(extra=1),'scene_pack_shape_invalid'),
            ('travel.json',lambda d:d.update(knowledge=[dict(id='k',source='http://x',verified_on='2026-11-01',review_by='2026-12-01')]),'scene_pack_knowledge_invalid'),
            ('travel.json',lambda d:d.update(knowledge=[dict(id='k',source='https://x',verified_on='2026-12-01',review_by='2026-11-01')]),'scene_pack_knowledge_dates_invalid'),
            ('switches.json',lambda d:d['scene_packs'].update(medical=False),'scene_switches_packs_invalid'),
            ('switches.json',lambda d:d.update(payments='no'),'scene_switches_flags_invalid'),
            ('switches.json',lambda d:d['cities']['business'].update(shenzhen=False),'scene_switches_cities_invalid'),
        ]
        for name,change,error in cases:
            with self.subTest(error=error):
                self.setUp();self.edit(name,change)
                with self.assertRaisesRegex(config.ScenePackError,error):
                    config.load_pack(name[:-5],self.directory) if name!='switches.json' else config.load_switches(self.directory)

    def test_duplicate_keys_fail_closed(self):
        path=self.directory/'switches.json'
        path.write_text(path.read_text().replace('"medical": false','"medical": false, "medical": true'))
        with self.assertRaisesRegex(config.ScenePackError,'duplicate_scene_pack_key'):config.load_switches(self.directory)


if __name__=='__main__':unittest.main()
