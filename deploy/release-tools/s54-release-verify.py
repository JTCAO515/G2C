"""Build 54: bind an app release to merged GitHub evidence and the existing HK image witness."""
from hashlib import sha256
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys

CODE = Path(__file__).resolve().parent
# Private state (gates, evidence, logs, tokens) stays outside the repository; see README.md.
STATE = Path(os.environ.get('G2C_RELEASE_STATE', '~/.local/share/g2c/b-server-smoke-20261118')).expanduser()
phase, source, primary_raw = sys.argv[1:]
primary = int(primary_raw)
release = runpy.run_path(str(CODE / 'prepare-release-20261119.py'))
context = release['main'].__globals__
transport = runpy.run_path(str(CODE / 's54-release-relay.py'))
policy = (STATE / 'policy-e0bea843-dfc8a8d8-20261127.json').read_bytes()
assert sha256(policy).hexdigest() == 'c449d04115f5911c5187c03e7a80032cc98627bd4647eb5d25ef251c9bdf7b7b'
require_source_abi = context['require_source_abi']
context['require_source_abi'] = lambda actual, _: require_source_abi(actual, json.loads(policy))

previous = json.loads((STATE / 'release-20261119-3820da8b-evidence.json').read_bytes())
records = {row['pr_number']: row for row in (previous['primary'], *previous['related'])}
# #1355 explicitly replaces the withdrawn #1342 evidence for the combined smoke cost.
del records[1342]
qualified = json.loads((STATE / 'release-20261119-86028c3f-evidence.json').read_bytes())
for row in (qualified['primary'], *qualified['related']):
    if row['pr_number'] in (1354, 1355):
        records[row['pr_number']] = row
records[1361] = dict(pr_number=1361, source='2abaed518328ef3f10005a7ba10a526cf2894131',
                     review_approved_head='208b5606495c8bd59321b91adb103030c100105a',
                     review_comment=7096162895)
verify_review = context['review']

def github(path):
    return json.loads(transport['github_read']('repos/JTCAO515/G2C/' + path))

def review(number):
    if number not in records:
        return verify_review(number)
    row = records[number]
    context['verify_release_review'](github, row['source'], row)
    return row

context.update(github=github, review=review, RELATED=())
if source != records[1361]['source'] and primary != 1355:
    planned = (
        (1381, 'b9a03866b1f383982a956a1c000ba9a1f96ef66f', 7098339208),
        (1382, '7767ae360c226908142d9f49edde843d1ca324d8', 7098352297),
        (1383, '6a64b0b4c7ac2cf65e746d493026fe7f97b71c24', 7098378764),
        (1396, '9dafb542dc50efa8af55e7be2a60d1a1a7f0e9f5', 7100967447),
        (1398, '550a5b504c83b0273d11347e94e978df88c564d6', 7101080504),
        (1402, 'e6fb1ad40d218dbc4dde84450bbc32fd0a5ef6cc', 7101022715),
        (1403, 'a806a404210be9da0f64b0f86a0fafa588f6fb32', 7102595211),
        (1405, 'f9ee4b54181d638e27a44aca3b64a6cd246957c5', 7104171872),
        (1412, '59c0ca71b6c185dc049b6ac1ce22a2e0bd47729b', 7113650004),
        (1413, 'a6aecee6ac2b086eeb8d8781fb97d2df9fc8fb4c', 7115086296),
        (1414, 'a5ff9f73490467652abceddac9f3c5cc82a29d77', 7115744999),
        (1415, '492031ca57c11cf49833c65a736501ace120cab9', 7115652353),
        # Build 54 (Claude S line). Post-merge independent reviews; #1422 is superseded by the
        # approved #1440, which re-reviewed the combined taxi search code.
        (1418, '964a1a1f5faec19df02ecaca3058341a19b780af', 7126265936),
        (1419, '84adcfa12582241244cbffdfb1514732cf0db61f', 7126266952),
        (1423, '5eb1215f666807ea821be85bcf083f5591228596', 7126267874),
        (1440, 'a0ba72ad089ca9be1250cc01cbb59b36a66e296a', 7126121556),
        # #1443 (bac59fce, review 7126546302) was verified as the primary of the f0bb784b release;
        # its merged test file also carries #1440's reviewed hunk, so it is not re-diffed here.
        (1444, '334f759caf452fdf2f518f7a7097abeae9f668c4', 7130259153),
        (1459, 'f1a68c8639a1b2c674a0ba393d77622cbd6ca2cc', 7131629507),
        (1462, '560307620754eeb247f740d1e16fbdec72769fc2', 7133433369),
        (1477, '8b3765fd19ae0e6bd8c74ed05626349a1d361e4a', 7137706463),
        (1478, '76db388060bd2c106cad21b9c1bb6f13ef6920ae', 7137712596),
        # e66c34fc release: CI and dialogue PRs merged after 7bf31c66 (each has an exact-head APPROVE).
        (1476, '54dab96c86103a56a0aa6b3d075d3a4a86b0127e', 7135606900),
        (1479, '90d6b5deadeab2f7071df24ef444c4ae74b1cebb', 7137734954),
        (1481, '29f1392358ab96da82afb31dd6efab3b25bf3e2c', 7138451355),
        (1485, '61e1fc994a8d3553df4d56ffa17bd4412f4ca1ac', 7138688845),
        (1486, '5cc7cba9087e7f2c1acbbed25e058d34a51cbc63', 7138866730),
        (1482, 'ea2533adeef6f9816b592496da2ed5a68502258d', 7138468121),
    )
    for number, head, review_id in planned:
        pr = github(f'pulls/{number}')
        if not pr['merged']:
            continue
        merged = pr['merge_commit_sha']
        included = subprocess.run(['git','merge-base','--is-ancestor',merged,source],check=False)
        if included.returncode == 1:
            continue
        assert included.returncode==0 and pr['head']['sha']==head
        names = [row['filename'] for row in github(f'pulls/{number}/files?per_page=100')]
        subprocess.run(['git','diff','--exit-code',head,merged,'--',*names],check=True)
        records[number] = dict(pr_number=number,source=merged,review_approved_head=head,
                               review_comment=review_id,reviewed_changed_blobs_equal=len(names))
extra = [1354, 1355, *records]
sys.argv = [sys.argv[0], phase, source, str(primary), *map(str, extra)]
release['main']()
