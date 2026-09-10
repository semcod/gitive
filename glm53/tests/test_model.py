import math
import random
import unittest
from intuition.model import embed, cos, default_state, validate_state, score, probabilities, select, update
from intuition.facts import frontier, validate_new, validate_fact
from intuition.llm import extract_json


def fact():
    return dict(id="f_0001", content="Wiedza o grafach", tags=["open"], references=[], source="seed", created="2026-09-10T00:00:00Z")


class ModelTests(unittest.TestCase):
    def test_embedding_normalized_deterministic(self):
        v = embed("Zażółć gęślą jaźń, teoria grafów")
        self.assertEqual(v, embed("Zażółć gęślą jaźń, teoria grafów"))
        self.assertAlmostEqual(cos(v, v), 1)
        self.assertEqual(embed("!"), [0.] * 256)

    def test_critic_formula_and_unique_references(self):
        f = fact()
        c = dict(archetype="derive", prompt=f["content"], rationale="", references=[f["id"], f["id"], "missing"])
        row = score(c, [f], [embed(f["content"])], default_state(), random.Random(1), {"derive": .5})
        self.assertAlmostEqual(row["feats"]["nov"], 0)
        self.assertAlmostEqual(row["feats"]["coh"], 1)
        self.assertEqual(row["feats"]["grn"], .5)
        self.assertAlmostEqual(row["U"], 2)

    def test_softmax_limits(self):
        rows = [{"U": 10000.}, {"U": -10000.}]
        self.assertEqual(probabilities(rows, .1), [1, 0])
        self.assertEqual(probabilities(rows, 0), [1, 0])
        self.assertAlmostEqual(probabilities(rows, 1e12)[0], .5, places=6)
        self.assertIs(select(rows, 0, random.Random(7)), rows[0])
        for rows, tau in (([], 1), (rows, -1)):
            with self.assertRaises(ValueError):
                probabilities(rows, tau)

    def test_learning(self):
        s = default_state(eta=.01)
        task = dict(archetype="derive", U=2., feats={k: .5 for k in s["w"]})
        update(s, task, 3)
        self.assertEqual(s["alpha"]["derive"], 4)
        self.assertEqual(s["beta"]["derive"], 1)
        self.assertGreater(s["w"]["nov"], 1)
        update(s, task, 0)
        self.assertEqual(s["beta"]["derive"], 2)
        validate_state(s)

    def test_state_rejects_nan_and_corruption(self):
        for k, v in (("tau", math.nan), ("m", 0), ("step", True)):
            s = default_state()
            s[k] = v
            with self.assertRaises(ValueError):
                validate_state(s)

    def test_frontier(self):
        first = fact()
        other = dict(first, id="f_0002", references=["missing"], tags=[], supersedes=first["id"])
        self.assertEqual(frontier([first, other]), dict(open=[], dangling=["missing"]))

    def test_schema_and_batch_dedup(self):
        raw = [{"content": "Nowe związki logiczne w systemie", "tags": ["hypothesis"], "references": []}]
        self.assertEqual(len(validate_new(raw + raw, [fact()])), 1)
        self.assertEqual(validate_new([{"content": "Wiedza o grafach", "tags": []}], [fact()]), [])
        self.assertEqual(validate_new([{"content": "abc", "tags": "bad"}], []), [])
        with self.assertRaises(ValueError):
            validate_fact(dict(fact(), id="../escape"))

    def test_json_fences_and_prose(self):
        self.assertEqual(extract_json('Tekst ```json\n[{"x": 1}]\n```'), [{"x": 1}])
        with self.assertRaises(ValueError):
            extract_json("nonsense")
