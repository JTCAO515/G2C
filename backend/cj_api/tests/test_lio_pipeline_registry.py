"""Production private native4 producers; public model tool lists stay unchanged."""
from types import SimpleNamespace
import unittest

from cj_api.real_services import RealTools
from cj_api.local_lio_provider_sources import POI2_REGISTRATION,ROUTE_REGISTRATION
from cj_usage.metered_exit import BudgetUnknown


class PipelineRegistry(unittest.TestCase):
    def tools(self,names=None):
        services=SimpleNamespace(subjects=frozenset({'m4-synthetic-registry'}),
            national_subjects=frozenset({'m4-synthetic-registry'}))
        return RealTools(services,**({}if names is None else dict(allowed_native=frozenset(names))))

    def test_production_registry_installs_private_producers_without_advertising_model_tools(self):
        tools=self.tools()
        self.assertIn(POI2_REGISTRATION,tools.registrations)
        self.assertIn(ROUTE_REGISTRATION,tools.registrations)
        public={row['function']['name']for row in tools.native_tools+tools.national_tools}
        self.assertNotIn(POI2_REGISTRATION,public)
        self.assertNotIn(ROUTE_REGISTRATION,public)
        with self.assertRaises(TypeError):tools.registrations['extra']=None

    def test_native_tool_subset_does_not_enable_other_private_place_producers(self):
        for names,poi,route in (({'weather'},False,False),({'place_search'},True,False),
                                ({'place_route'},False,True)):
            tools=self.tools(names)
            self.assertEqual(POI2_REGISTRATION in tools.registrations,poi)
            self.assertEqual(ROUTE_REGISTRATION in tools.registrations,route)

    def test_model_json_cannot_supply_a_python_origin_or_registered_source_capability(self):
        tools=self.tools()
        for registration in (POI2_REGISTRATION,ROUTE_REGISTRATION):
            with self.subTest(registration=registration),self.assertRaises(BudgetUnknown):
                tools.registrations[registration].prepare_input({'query':'北京','origin':{},'sources':{}})


if __name__=='__main__':unittest.main()
