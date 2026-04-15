import json
from collections import deque

MIN_ANSWERS = 5
MAX_DIAGNOSES = 5


class FactBase:
    def __init__(self):
        self.facts = {}
        self.unknown = set()

    def assert_fact(self, sid, val):
        self.facts[sid] = val

    def mark_unknown(self, sid):
        self.unknown.add(sid)
        self.facts[sid] = None

    def get(self, sid):
        return self.facts.get(sid)

    def count_all(self):
        return len(self.facts)

    def clear(self):
        self.facts.clear()
        self.unknown.clear()


class InferenceEngine:
    def __init__(self, rules):
        self.rules = rules

    def evaluate_rule(self, rule, fb):
        conditions = rule["conditions"]
        unknown_count = 0
        known_count = 0
        base_conf = rule.get("confidence", 0.8)

        for sid, expected in conditions.items():
            actual = fb.get(sid)

            if actual is None:
                unknown_count += 1
            elif actual == expected:
                known_count += 1
            else:
                return False, 0.0

        if known_count == 0:
            return False, 0.0

        confidence = base_conf * (known_count / len(conditions))
        confidence *= (1 - 0.05 * unknown_count)

        return True, round(confidence, 3)

    def run(self, fb, skip_min=False):

        if not skip_min and fb.count_all() < MIN_ANSWERS:
            raise ValueError(f"Minimum {MIN_ANSWERS} réponses requises")

        results = []

        for rule in self.rules:
            matched, conf = self.evaluate_rule(rule, fb)

            if matched:
                results.append({
                    "rule_id": rule["id"],
                    "category": rule["category"],
                    "severity": rule.get("severity", "medium"),
                    "conclusion": rule["conclusion"],
                    "solution": rule["solution"],
                    "confidence": conf,
                    "conditions": rule["conditions"],
                    "sources": rule.get("sources", [])
                })

        results.sort(key=lambda d: d["confidence"], reverse=True)

        return results[:MAX_DIAGNOSES]

    def live_preview(self, fb):

        results = []

        for rule in self.rules:

            matched, conf = self.evaluate_rule(rule, fb)

            if matched and conf > 0.3:
                results.append({
                    "rule_id": rule["id"],
                    "conclusion": rule["conclusion"][:60],
                    "confidence": conf,
                    "category": rule["category"]
                })

        results.sort(key=lambda d: d["confidence"], reverse=True)

        return results[:3]

    def detect_inconsistencies(self, fb):

        facts = fb.facts
        issues = []

        if facts.get("pc_ne_demarre_pas") and facts.get("pc_fonctionne"):
            issues.append("❌ Contradiction : PC ne démarre pas ET semble fonctionner.")

        if facts.get("ecran_noir") and facts.get("artefacts_visuels"):
            issues.append("❌ Contradiction : Écran noir ET artefacts visuels visibles.")

        if facts.get("bruits_cliquetis") and facts.get("pc_lent") is False:
            issues.append("⚠️ Incohérence : Cliquetis disque MAIS PC non lent.")

        if facts.get("surchauffe") and facts.get("bruit_ventilateur_fort") is False:
            issues.append("⚠️ Incohérence : Surchauffe MAIS ventilateurs silencieux.")

        if facts.get("virus_detecte") and facts.get("pc_lent") is False and facts.get("applications_ne_s_ouvrent_pas") is False:
            issues.append("ℹ️ Virus détecté mais aucun symptôme actif visible.")

        if facts.get("batterie_ne_charge_pas") and facts.get("chargeur_fonctionnel") is False:
            issues.append("ℹ️ Batterie ne charge pas ET chargeur défaillant.")

        return issues

    def _build_graph(self, question_tree):

        graph = {}

        children_map = question_tree.get("children", {})
        all_nodes = set(question_tree.get("root_questions", []))

        for node, data in children_map.items():
            all_nodes.add(node)

            if "children" in data:
                for child in data["children"]:
                    all_nodes.add(child)

        for node in all_nodes:
            graph[node] = []

        for parent, data in children_map.items():

            if "children" in data:

                expected = data.get("condition")

                for child in data["children"]:
                    graph[parent].append((child, expected))

        for node, data in children_map.items():

            if "parent" in data and "condition" in data:

                parent = data["parent"]
                expected = data["condition"]

                if parent in graph:
                    graph[parent].append((node, expected))

        return graph

    def is_question_valid(self, qid, fb):

        facts = fb.facts

        if qid == "pc_s_eteint_seul" and facts.get("pc_ne_demarre_pas") is True:
            return False

        if qid == "pc_fonctionne" and facts.get("pc_ne_demarre_pas") is True:
            return False

        if qid == "ecran_noir" and facts.get("pc_ne_demarre_pas") is True:
            return False

        return True

    def next_question(self, fb, question_tree, all_sids):

        answered = set(fb.facts.keys())
        graph = self._build_graph(question_tree)

        active_roots = []

        for root in question_tree.get("root_questions", []):

            val = fb.get(root)

            if val is True:
                active_roots.append(root)

        if not active_roots:

            for root in question_tree.get("root_questions", []):

                if root not in answered:
                    return root

        queue = deque(active_roots)
        visited = set()

        candidates = []

        while queue:

            node = queue.popleft()

            if node in visited:
                continue

            visited.add(node)

            if node not in answered:

                if self.is_question_valid(node, fb):
                    candidates.append(node)

                continue

            answer = fb.get(node)

            for child, expected in graph.get(node, []):

                if expected is None or answer == expected:
                    queue.append(child)

        scored = []

        for q in candidates:

            score = 0

            for rule in self.rules:

                if q in rule["conditions"]:
                    score += 2

            if q in graph:
                score += len(graph[q])

            scored.append((q, score))

        scored.sort(key=lambda x: x[1], reverse=True)

        if scored:
            return scored[0][0]

        for sid in sorted(all_sids):

            if sid not in answered:
                return sid

        return None

    def get_all_symptom_ids(self):

        sids = set()

        for r in self.rules:

            for sid in r["conditions"]:
                sids.add(sid)

        return sids


_engine = None
_fb = FactBase()
_questions_map = {}
_question_tree = {}
_all_sids = set()
_categories = []


def load_rules(json_str):

    global _engine, _all_sids

    data = json.loads(json_str)

    _engine = InferenceEngine(data["rules"])

    _all_sids = _engine.get_all_symptom_ids()

    return json.dumps({
        "rules_count": len(data["rules"])
    })


def load_questions(json_str):

    global _questions_map, _question_tree, _categories

    data = json.loads(json_str)

    _questions_map = {
        q["id"]: q for q in data["symptom_questions"]
    }

    _question_tree = data.get("question_tree", {})
    _categories = data.get("categories", [])

    return json.dumps({
        "symptoms_count": len(_questions_map),
        "categories": [c["id"] for c in _categories]
    })


def reset_session():

    global _fb

    _fb = FactBase()

    return "ok"


def answer_question(sid, val_str):

    if val_str == "yes":
        _fb.assert_fact(sid, True)

    elif val_str == "no":
        _fb.assert_fact(sid, False)

    else:
        _fb.mark_unknown(sid)

    return "ok"


def get_next_question():

    qid = _engine.next_question(_fb, _question_tree, _all_sids)

    if qid is None:
        return json.dumps(None)

    q_info = _questions_map.get(qid, {})

    return json.dumps({
        "id": qid,
        "question": q_info.get("question", qid),
        "category": q_info.get("category", "")
    })


def get_live_preview():

    candidates = _engine.live_preview(_fb)

    return json.dumps(candidates)


def get_answers_count():

    return _fb.count_all()


def run_diagnosis():

    try:

        results = _engine.run(_fb)

        inconsistencies = _engine.detect_inconsistencies(_fb)

        return json.dumps({
            "diagnoses": results,
            "inconsistencies": inconsistencies,
            "answers_count": _fb.count_all()
        })

    except ValueError as e:

        return json.dumps({
            "error": str(e)
        })


def add_rule_py(rule_json_str):

    global _all_sids

    try:

        rule = json.loads(rule_json_str)

        if any(r["id"] == rule["id"] for r in _engine.rules):
            return json.dumps({"error": "ID déjà utilisé"})

        _engine.rules.append(rule)

        _all_sids = _engine.get_all_symptom_ids()

        return json.dumps({
            "ok": True,
            "count": len(_engine.rules)
        })

    except Exception as e:

        return json.dumps({
            "error": str(e)
        })


def delete_rule_py(rule_id):

    before = len(_engine.rules)

    _engine.rules = [
        r for r in _engine.rules
        if r["id"] != rule_id
    ]

    if len(_engine.rules) == before:
        return json.dumps({
            "error": f"Règle {rule_id} introuvable"
        })

    global _all_sids

    _all_sids = _engine.get_all_symptom_ids()

    return json.dumps({
        "ok": True,
        "count": len(_engine.rules)
    })