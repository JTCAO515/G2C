"""Controlled calculator fixtures only; no actual network or provider evidence."""
from copy import deepcopy
import unittest

import test_gates
from gates import POLICY, MAC_VPN_NETWORK
from report import report, markdown
from evaluate import InputError


class NetworkPolicyChecks(unittest.TestCase):
    def setUp(self):
        fixture=test_gates.GateChecks();fixture.setUp()
        self.plan=fixture.plan
        network=self.plan['networks'][1]
        self.plan['networks']=[network]
        self.rows=[r for r in fixture.rows if r['network_id']==network['id']]
        self.plan['network_policy']=MAC_VPN_NETWORK['id']
        network.update(client_device='codex_development_mac',client_location='china_mainland',vpn='on')
        network['measurement'].update(scope='user_submission_to_answer',clock='client_monotonic')

    def test_new_approved_condition_retains_all_planned_tasks_and_limits(self):
        result=report(self.plan,self.rows)
        quality=result['quality_acceptance']
        self.assertEqual(quality['evaluation_release_decision'],'PASS')
        self.assertEqual(quality['candidates'][0]['missing_target_phases'],{})
        self.assertEqual(sum(p['planned_attempt_n'] for p in quality['profiles']),len(self.rows))
        for key in ('completion_rate_minimum','serious_errors_maximum',
                    'first_body_p95_maximum_seconds','full_answer_p95_maximum_seconds'):
            self.assertEqual(quality['policy'][key],POLICY[key])
        self.assertEqual(quality['policy']['network_policy']['id'],MAC_VPN_NETWORK['id'])
        self.assertIn(MAC_VPN_NETWORK['id'],markdown(result))

    def test_historical_missing_region_semantics_are_not_reinterpreted(self):
        for selection in (None,POLICY['id']):
            plan=deepcopy(self.plan)
            if selection is None:del plan['network_policy']
            else:plan['network_policy']=selection
            result=report(plan,self.rows)
            candidate=result['quality_acceptance']['candidates'][0]
            self.assertEqual(candidate['missing_target_phases'],{'overseas_pretrip':'UNRUN'})
            self.assertEqual(candidate['evaluation_release_decision'],'UNKNOWN')
            self.assertEqual(result['quality_acceptance']['policy'],POLICY)

    def test_hk_server_phone_unknown_vpn_or_wrong_clocks_do_not_cover_mac(self):
        for field,value in (('client_device','iphone'),('client_location','hong_kong'),('vpn','UNKNOWN'),
                            ('client_device',None),('client_location',None),('vpn',None)):
            plan=deepcopy(self.plan);plan['networks'][0][field]=value
            result=report(plan,self.rows)
            self.assertEqual(result['quality_acceptance']['evaluation_release_decision'],'UNKNOWN')
        for field,value in (('scope','read_snapshot'),('scope',None),('clock','server_monotonic'),('clock',None)):
            plan=deepcopy(self.plan);plan['networks'][0]['measurement'][field]=value
            self.assertEqual(report(plan,self.rows)['quality_acceptance']['evaluation_release_decision'],'UNKNOWN')

    def test_read_only_diagnostic_and_missing_observations_cannot_certify(self):
        plan=deepcopy(self.plan);plan['networks'][0]['kind']='target_network_read_diagnostic'
        self.assertEqual(report(plan,self.rows)['quality_acceptance']['evaluation_release_decision'],'UNKNOWN')
        result=report(self.plan,[])
        self.assertEqual(result['quality_acceptance']['evaluation_release_decision'],'UNRUN')
        self.assertEqual(sum(p['outcomes']['UNRUN'] for p in result['quality_acceptance']['profiles']),len(self.rows))
        plan=deepcopy(self.plan);plan['evidence_layer']='synthetic'
        self.assertEqual(report(plan,self.rows)['quality_acceptance']['evaluation_release_decision'],'UNRUN')

    def test_policy_selection_does_not_override_failures_or_invent_authority(self):
        for value in ('custom',None,{'required_target_phases':[]}):
            plan=deepcopy(self.plan);plan['network_policy']=value
            with self.assertRaises(InputError):report(plan,self.rows)
        plan=deepcopy(self.plan);plan['approved_thresholds']={'first_body_p95_maximum_seconds':999}
        rows=deepcopy(self.rows);rows[0]['first_body_seconds']=6
        self.assertEqual(report(plan,rows)['quality_acceptance']['evaluation_release_decision'],'FAIL')
        rows=deepcopy(self.rows);rows[0]['serious_errors']=[dict(kind='program',ref='synthetic:original',
            description='Controlled original severe error',resolved=True)]
        self.plan['attempts']=[1,2]
        repeated=[deepcopy(r)|dict(attempt=2) for r in self.rows]
        result=report(self.plan,rows+repeated)
        self.assertEqual(result['quality_acceptance']['evaluation_release_decision'],'FAIL')


if __name__=='__main__':unittest.main(verbosity=2)
