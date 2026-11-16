"""Check planning evidence without changing backlog or estimating readiness by prose."""
import csv
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def load(path):
    with (ROOT/path).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def evidence(path):return bool(path) and (ROOT/path.split('#')[0]).is_file()
def check():
    stories={r['story_id']:r for r in load('lr06_backlog/backlog.csv')}
    estimates={r['story_id']:r['final_estimate'] for r in load('lr08_poker/estimates.csv')}
    criteria={r['criterion_id']:r['accepted_by'] for r in load('lr05_charter/success_criteria.csv')}
    stakeholders={r['stakeholder_id'] for r in load('lr05_charter/stakeholders.csv')}
    result=[]
    for r in load('lr06_backlog/planning_readiness.csv'):
        s=stories[r['story_id']];missing=[]
        if not all(s[k] for k in ['as_a','i_want','so_that','success_criterion']) or not r['sprint_goal']:missing.append('goal/value')
        if len([a for a in s['acceptance_criteria'].split(';') if a.strip()])<2 or not evidence(r['scenario_ref']):missing.append('AC/scenario')
        if not evidence(r['fixture_ref']) or not evidence(r['dependency_evidence']) or r['dependency_status'] not in ['confirmed_local_fixture','confirmed_external']:missing.append('dependency/fixture')
        estimate=estimates.get(r['story_id'],'')
        if not estimate.isdigit() or not 1<=int(estimate)<=8 or estimate!=r['estimate']:missing.append('estimate1..8')
        if r['acceptor_id'] not in stakeholders or r['acceptor_id']!=criteria.get(s['success_criterion']) or r['open_questions']!='none_in_declared_scope':missing.append('acceptor/questions')
        ready=not missing
        if (r['ready']=='yes')!=ready:raise ValueError('Ready flag differs from evidence: '+r['story_id'])
        result.append((r['story_id'],ready,missing))
    return result
if __name__=='__main__':
    for sid,ready,missing in check():print(sid,'READY' if ready else 'NOT READY',', '.join(missing))
