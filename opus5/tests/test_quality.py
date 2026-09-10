from intuition.propose import eligible, build_prompt, active_facts
from intuition.api_guard import validate_python_api


def test_scope_and_current_code_in_prompt():
    code={'src/core.py':'def taxed(a,b): return a+b'}
    valid=dict(title='Fix tax',body='taxed(200,23) returns 246',cost=1,files=['src/core.py'])
    assert eligible(valid,code)
    assert not eligible({**valid,'files':['tests/test_tax.py']},code)
    assert not eligible({**valid,'body':'acceptance_placeholder_2'},code)
    assert code['src/core.py'] in build_prompt('goal',[],[],2,code=code)
    assert 'Only propose changes' in build_prompt('goal',[],[],2,code=code)


def test_retired_observations_not_ranked_again():
    facts=[{'id':'old','kind':'ci_failure'},{'id':'current','supersedes':'old'}]
    assert active_facts(facts)==[facts[1]]
    assert len(facts)==2


def test_python_api_guard_including_constructor():
    for before,after in [('def taxed(a,b): return a+b','def taxed(a,b,c=None): return a+b'),
                         ('class A:\n def __init__(self,x): pass','class A:\n def __init__(self,x,y=None): pass')]:
        try: validate_python_api('src/core.py',before,after)
        except ValueError: pass
        else: raise AssertionError('signature drift accepted')
    validate_python_api('src/core.py','def taxed(a,b): return a+b','def taxed(a,b): return a*(1+b/100)')
