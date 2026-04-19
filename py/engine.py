"""
SysDiag — Moteur d'inférence par chaînage avant.
Architecture : dual-filter (screening racine + déclencheurs de dépendances).
Conçu pour Pyodide/WASM — aucune dépendance externe.
"""

import json

# ─── Constantes ────────────────────────────────────────────────────────────────

MIN_ANSWERS   = 5
MAX_DIAGNOSES = 5
UNKNOWN_PENALTY = 0.10   # réduction de confiance par condition inconnue


# ─── Base de faits ─────────────────────────────────────────────────────────────

class FactBase:
    def __init__(self):
        self.facts: dict = {}

    def set(self, sid: str, val):
        """val: True | False | None (inconnu)"""
        self.facts[sid] = val

    def get(self, sid: str):
        return self.facts.get(sid, "ABSENT")   # distingue absent de None

    def answered(self) -> int:
        return len(self.facts)

    def clear(self):
        self.facts.clear()


# ─── Moteur d'inférence ────────────────────────────────────────────────────────

class InferenceEngine:

    def __init__(self, rules, questions_map, screening_order,
                 question_triggers, inconsistency_rules, contradictions):
        self.rules               = rules
        self.questions_map       = questions_map
        self.screening_order     = screening_order
        self.question_triggers   = question_triggers
        self.inconsistency_rules = inconsistency_rules
        self.contradictions      = contradictions

        # ── Blocage conditionnel : si condition=True → ignorer ces questions ──
        self.skip_if = {
            "pc_ne_demarre_pas": [
                # Réseau — impossible si le PC ne démarre pas
                "pas_internet", "internet_lent", "connexion_coupe_regulierement",
                "wifi_connecte", "signal_wifi_visible", "autres_appareils_fonctionnent",
                "loin_du_routeur", "beaucoup_appareils_connectes", "fai_probleme",
                # Audio/périphériques — nécessitent Windows actif
                "pas_de_son", "clavier_ne_fonctionne_pas", "souris_ne_fonctionne_pas",
                "usb_non_detecte", "imprimante_ne_fonctionne_pas",
                "batterie_ne_charge_pas", "batterie_se_decharge_vite",
                # Performance/système — nécessitent un OS chargé
                "pc_lent", "pc_gele", "ecran_bleu_bsod",
                "jeux_lents", "applications_ne_s_ouvrent_pas",
                "bureau_ne_s_affiche_pas", "mises_a_jour_echouent",
                # Extinction spontanée ≠ ne démarre pas du tout
                "pc_s_eteint_seul",
                # Messages démarrage impossibles si rien ne s'allume
                "erreurs_demarrage", "windows_ne_demarre_pas",
                "message_boot_device_not_found", "pc_redemarre_en_boucle",
                "apres_mise_a_jour", "message_erreur_demarrage_specific",
            ],
            "ecran_noir": [
                # Écran totalement noir exclut tout contenu visuel
                "ecran_pixelise", "artefacts_visuels",
            ],
            "pas_internet": [
                # Pas internet et lent sont mutuellement exclusifs
                "internet_lent", "connexion_coupe_regulierement",
            ],
        }

    # ── Évaluation d'une règle ────────────────────────────────────────────────

    def _eval_rule(self, rule: dict, fb: FactBase):
        """Retourne (match: bool, confidence: float)"""
        conditions  = rule.get("conditions", {})
        known_ok    = 0
        unknown_cnt = 0
        base_conf   = rule.get("confidence", 0.8)

        for sid, expected in conditions.items():
            val = fb.get(sid)
            if val == "ABSENT":
                unknown_cnt += 1
            elif val is None:
                unknown_cnt += 1
            elif val == expected:
                known_ok += 1
            else:
                return False, 0.0   # contradiction explicite → rejet

        if known_ok == 0:
            return False, 0.0       # rien de confirmé → pas de match

        conf = base_conf * (1.0 - UNKNOWN_PENALTY * unknown_cnt)
        return True, round(conf, 3)

    # ── Sélection de la prochaine question ────────────────────────────────────

    def next_question(self, fb: FactBase) -> dict | None:
        answered = set(fb.facts.keys())

        # Calcule les questions à ignorer selon les faits actuels
        blocked = set()
        for condition_sid, skip_list in self.skip_if.items():
            if fb.get(condition_sid) == True:
                blocked.update(skip_list)

        # 1. Questions déclenchées par les réponses actuelles (dépendances)
        triggered = []
        for qid, triggers in self.question_triggers.items():
            if qid in answered or qid in blocked:
                continue
            for t in triggers:
                if fb.get(t["question"]) == t["value"]:
                    triggered.append(qid)
                    break

        if triggered:
            scored = sorted(triggered, key=lambda q: self._rule_coverage(q), reverse=True)
            for qid in scored:
                if qid in self.questions_map:
                    return self.questions_map[qid]

        # 2. Fallback : screening racine dans l'ordre prévu
        for qid in self.screening_order:
            if qid not in answered and qid in self.questions_map and qid not in blocked:
                return self.questions_map[qid]

        return None

    def _rule_coverage(self, qid: str) -> int:
        return sum(1 for r in self.rules if qid in r.get("conditions", {}))

    # ── Aperçu en temps réel ──────────────────────────────────────────────────

    def live_preview(self, fb: FactBase) -> list:
        results = []
        for rule in self.rules:
            match, conf = self._eval_rule(rule, fb)
            if match and conf > 0.25:
                results.append({
                    "rule_id":    rule["id"],
                    "conclusion": rule["conclusion"][:55],
                    "confidence": conf,
                    "category":   rule.get("category", ""),
                })
        results.sort(key=lambda d: d["confidence"], reverse=True)
        return results[:3]

    # ── Diagnostic complet ────────────────────────────────────────────────────

    def run(self, fb: FactBase) -> list:
        if fb.answered() < MIN_ANSWERS:
            raise ValueError(f"Minimum {MIN_ANSWERS} réponses requises ({fb.answered()} données).")

        results = []
        for rule in self.rules:
            match, conf = self._eval_rule(rule, fb)
            if match:
                results.append({
                    "rule_id":    rule["id"],
                    "category":   rule.get("category", ""),
                    "severity":   rule.get("severity", "medium"),
                    "conclusion": rule["conclusion"],
                    "solution":   rule["solution"],
                    "confidence": conf,
                    "conditions": rule.get("conditions", {}),
                    "sources":    rule.get("sources", []),
                })

        results.sort(key=lambda d: d["confidence"], reverse=True)
        return results[:MAX_DIAGNOSES]

    # ── Détection d'incohérences ──────────────────────────────────────────────

    def detect_inconsistencies(self, fb: FactBase) -> list:
        msgs = []
        for rule in self.inconsistency_rules:
            if all(fb.get(k) == v for k, v in rule.get("if", {}).items()):
                msgs.append(rule["message"])
        for c in self.contradictions:
            if all(fb.get(k) == v for k, v in c.get("conditions", {}).items()):
                msgs.append(c["message"])
        return msgs


# ─── État global (accessible depuis JS via Pyodide) ────────────────────────────

_engine: InferenceEngine | None = None
_fb     = FactBase()
_rules_raw = []


# ─── API publique appelée depuis JS ────────────────────────────────────────────

def load_data(rules_json: str, questions_json: str,
              flow_json: str, conditions_json: str) -> str:
    """Charge toutes les données et initialise le moteur."""
    global _engine, _rules_raw

    rules_data      = json.loads(rules_json)
    questions_data  = json.loads(questions_json)
    flow_data       = json.loads(flow_json)
    conditions_data = json.loads(conditions_json)

    _rules_raw = rules_data.get("rules", rules_data if isinstance(rules_data, list) else [])

    raw_q = questions_data.get("symptom_questions", questions_data if isinstance(questions_data, list) else [])
    questions_map = {q["id"]: q for q in raw_q}

    screening_order     = flow_data.get("screening_order", [])
    question_triggers   = flow_data.get("question_triggers", {})
    contradictions      = flow_data.get("contradictions", [])
    inconsistency_rules = conditions_data.get("inconsistency_rules", [])

    _engine = InferenceEngine(
        rules               = _rules_raw,
        questions_map       = questions_map,
        screening_order     = screening_order,
        question_triggers   = question_triggers,
        inconsistency_rules = inconsistency_rules,
        contradictions      = contradictions,
    )

    categories = sorted({r.get("category", "") for r in _rules_raw if r.get("category")})

    return json.dumps({
        "rules_count":    len(_rules_raw),
        "symptoms_count": len(questions_map),
        "categories":     categories,
        "min_answers":    MIN_ANSWERS,
        "max_diagnoses":  MAX_DIAGNOSES,
    })


def reset_session() -> str:
    _fb.clear()
    return "ok"


def answer_question(sid: str, val_str: str) -> str:
    """
    Enregistre la réponse ET vérifie immédiatement les contradictions.
    Retourne JSON {"status":"ok","warnings":[...]} pour alerter le JS en temps réel.
    """
    val = True if val_str == "yes" else (False if val_str == "no" else None)
    _fb.set(sid, val)

    # Vérification immédiate — pas seulement en fin de session
    warnings = _engine.detect_inconsistencies(_fb) if _engine else []
    return json.dumps({"status": "ok", "warnings": warnings})


def get_next_question() -> str:
    if _engine is None:
        return json.dumps(None)
    q = _engine.next_question(_fb)
    return json.dumps(q)


def get_live_preview() -> str:
    if _engine is None:
        return json.dumps([])
    return json.dumps(_engine.live_preview(_fb))


def get_answers_count() -> int:
    return _fb.answered()


def run_diagnosis() -> str:
    if _engine is None:
        return json.dumps({"error": "Moteur non initialisé."})
    try:
        results         = _engine.run(_fb)
        inconsistencies = _engine.detect_inconsistencies(_fb)
        return json.dumps({
            "diagnoses":       results,
            "inconsistencies": inconsistencies,
            "answers_count":   _fb.answered(),
        })
    except ValueError as e:
        return json.dumps({"error": str(e)})


def add_rule_py(rule_json_str: str) -> str:
    try:
        rule = json.loads(rule_json_str)
        if any(r["id"] == rule["id"] for r in _engine.rules):
            return json.dumps({"error": "ID déjà utilisé"})
        _engine.rules.append(rule)
        _rules_raw.append(rule)
        return json.dumps({"ok": True, "count": len(_engine.rules)})
    except Exception as e:
        return json.dumps({"error": str(e)})


def delete_rule_py(rule_id: str) -> str:
    before = len(_engine.rules)
    _engine.rules = [r for r in _engine.rules if r["id"] != rule_id]
    if len(_engine.rules) == before:
        return json.dumps({"error": f"Règle {rule_id} introuvable"})
    return json.dumps({"ok": True, "count": len(_engine.rules)})