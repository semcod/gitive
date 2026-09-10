"""Deterministic numerical probe used only by the cross-language comparison."""
import json, sys
from engine import rank, information_gain
x = json.load(sys.stdin)
print(json.dumps({'ranking':rank(x['state'],x['tasks']),
                  'gains':[information_gain(*v) for v in x['cases']]}))
