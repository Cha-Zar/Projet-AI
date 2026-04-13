"""
Module: inference_engine.py
Moteur d'inférence par chaînage avant (Forward Chaining)
Système Expert de Diagnostic de Panne Informatique
"""

import json
from pathlib import Path


# ======== CONSTANTES ========
MIN_ANSWERS = 5    # ★ Minimum de réponses (OUI/NON/INCONNU) avant diagnostic
MAX_DIAGNOSES = 5  # ★ Maximum de diagnostics retournés


class KnowledgeBase:
    """Charge et gère la base de connaissances (règles)."""

    def __init__(self, rules_path: str = None):
        if rules_path is None:
            rules_path = Path(__file__).parent.parent / "data" / "rules.json"
        with open(rules_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.rules = data["rules"]
        self.symptom_questions = {q["id"]: q for q in data["symptom_questions"]}
        self.categories = data["categories"]

    def get_rule(self, rule_id: str) -> dict:
        for r in self.rules:
            if r["id"] == rule_id:
                return r
        return None

    def add_rule(self, rule: dict) -> None:
        """Ajouter dynamiquement une règle."""
        self.rules.append(rule)

    def remove_rule(self, rule_id: str) -> bool:
        """Supprimer une règle dynamiquement."""
        before = len(self.rules)
        self.rules = [r for r in self.rules if r["id"] != rule_id]
        return len(self.rules) < before


class FactBase:
    """Gère la base de faits (réponses de l'utilisateur pour la session)."""

    def __init__(self):
        self.facts: dict = {}
        self.unknown: set = set()

    def assert_fact(self, symptom_id: str, value: bool) -> None:
        self.facts[symptom_id] = value

    def mark_unknown(self, symptom_id: str) -> None:
        self.unknown.add(symptom_id)
        self.facts[symptom_id] = None  # None = inconnu

    def get(self, symptom_id: str):
        return self.facts.get(symptom_id)

    def is_known(self, symptom_id: str) -> bool:
        return symptom_id in self.facts and self.facts[symptom_id] is not None

    def count_all_answers(self) -> int:
        """★ Compte toutes les réponses données : OUI, NON et INCONNU."""
        return len(self.facts)

    def clear(self) -> None:
        self.facts.clear()
        self.unknown.clear()


class InferenceEngine:
    """
    Moteur d'inférence par chaînage avant.
    Évalue les règles en fonction des faits connus et retourne des diagnostics.
    """

    def __init__(self, knowledge_base: KnowledgeBase):
        self.kb = knowledge_base

    def evaluate_rule(self, rule: dict, fact_base: FactBase) -> tuple[bool, float]:
        """
        Évalue une règle contre la base de faits.

        Logique corrigée :
        - Contradiction explicite (réponse ≠ attendu) → rejet immédiat.
        - Inconnu (None) → pas de rejet, confiance réduite de 10% par inconnu.
        - ★ Si 0 réponse ferme parmi les conditions → rejet
          (évite un diagnostic sur 100% d'inconnus).

        Retourne (match: bool, confidence_score: float).
        """
        conditions = rule["conditions"]
        unknown_count = 0
        known_count = 0
        base_confidence = rule.get("confidence", 0.8)

        for symptom_id, expected_value in conditions.items():
            actual = fact_base.get(symptom_id)

            if actual is None:
                # Inconnu : pénalité confiance uniquement
                unknown_count += 1
            elif actual == expected_value:
                # Condition satisfaite
                known_count += 1
            else:
                # ★ Contradiction explicite → règle rejetée immédiatement
                return False, 0.0

        # ★ Aucune réponse ferme = tout inconnu → rejet
        if known_count == 0:
            return False, 0.0

        # Réduction de confiance proportionnelle aux inconnus
        confidence = base_confidence * (1 - 0.1 * unknown_count)
        return True, round(confidence, 2)

    def run(self, fact_base: FactBase, skip_min_check: bool = False) -> list[dict]:
        """
        Lance le chaînage avant : évalue toutes les règles.

        ★ Vérifie MIN_ANSWERS réponses (OUI/NON/INCONNU) avant de diagnostiquer.
        ★ Retourne au maximum MAX_DIAGNOSES diagnostics triés par confiance.

        Args:
            fact_base: La base de faits courante.
            skip_min_check: Si True, ignore la vérification du minimum.

        Returns:
            Liste des diagnostics déclenchés (max MAX_DIAGNOSES).
        """
        # ★ Vérification du minimum de réponses
        if not skip_min_check:
            total_answered = fact_base.count_all_answers()
            if total_answered < MIN_ANSWERS:
                raise ValueError(
                    f"Pas assez de réponses : {total_answered}/{MIN_ANSWERS}. "
                    f"Répondez à au moins {MIN_ANSWERS} questions (OUI, NON ou INCONNU)."
                )

        diagnoses = []

        for rule in self.kb.rules:
            matched, confidence = self.evaluate_rule(rule, fact_base)
            if matched:
                diagnoses.append({
                    "rule_id": rule["id"],
                    "category": rule["category"],
                    "conclusion": rule["conclusion"],
                    "solution": rule["solution"],
                    "confidence": confidence,
                    "conditions_used": list(rule["conditions"].keys())
                })

        # Tri par confiance décroissante
        diagnoses.sort(key=lambda d: d["confidence"], reverse=True)

        # ★ Limiter aux MAX_DIAGNOSES premiers résultats
        return diagnoses[:MAX_DIAGNOSES]

    def get_missing_symptoms(self, fact_base: FactBase) -> list[str]:
        """
        Retourne la liste des symptômes qui pourraient déclencher de nouvelles règles
        mais n'ont pas encore été renseignés.
        """
        known = set(fact_base.facts.keys())
        missing = set()
        for rule in self.kb.rules:
            for symptom_id in rule["conditions"]:
                if symptom_id not in known:
                    missing.add(symptom_id)
        return list(missing)

    def explain(self, diagnosis: dict, fact_base: FactBase) -> str:
        """
        Génère une explication textuelle du raisonnement menant à un diagnostic.
        """
        lines = []
        lines.append(f"📋 Règle déclenchée : {diagnosis['rule_id']}")
        lines.append(f"📂 Catégorie : {diagnosis['category']}")
        lines.append("")
        lines.append("🔍 Raisonnement (conditions vérifiées) :")

        rule = self.kb.get_rule(diagnosis["rule_id"])
        if rule:
            for symptom_id, expected in rule["conditions"].items():
                actual = fact_base.get(symptom_id)
                q = self.kb.symptom_questions.get(symptom_id, {})
                question_text = q.get("question", symptom_id)
                status = "✅" if actual == expected else "❓ (inconnu)"
                expected_str = "OUI" if expected else "NON"
                lines.append(f"  {status} {question_text} → attendu : {expected_str}")

        lines.append("")
        lines.append(f"🎯 Conclusion : {diagnosis['conclusion']}")
        lines.append(f"📊 Niveau de confiance : {int(diagnosis['confidence'] * 100)}%")
        lines.append("")
        lines.append(f"💡 Solution recommandée :")
        lines.append(f"   {diagnosis['solution']}")

        return "\n".join(lines)


def run_cli_session():
    """Interface ligne de commande simple pour tester le moteur."""
    print("\n" + "="*60)
    print("  SYSTÈME EXPERT — DIAGNOSTIC DE PANNE INFORMATIQUE")
    print("  FST / Département SI — Fondements de l'IA")
    print(f"  Minimum {MIN_ANSWERS} réponses · Max {MAX_DIAGNOSES} diagnostics")
    print("="*60)
    print("\nRépondez aux questions par O (oui), N (non) ou ? (inconnu)\n")

    kb = KnowledgeBase()
    fb = FactBase()
    engine = InferenceEngine(kb)

    asked = set()
    max_questions = 20
    count = 0

    while count < max_questions:
        missing = engine.get_missing_symptoms(fb)
        if not missing:
            break

        symptom_id = missing[0]
        if symptom_id in asked:
            break
        asked.add(symptom_id)

        q_info = kb.symptom_questions.get(symptom_id)
        if not q_info:
            continue

        total_answered = fb.count_all_answers()
        status = f"[{total_answered}/{MIN_ANSWERS}]" if total_answered < MIN_ANSWERS else f"[{total_answered} ✓]"

        while True:
            answer = input(f"{status} Q{count+1}. {q_info['question']} (O/N/?) : ").strip().upper()
            if answer == "O":
                fb.assert_fact(symptom_id, True)
                break
            elif answer == "N":
                fb.assert_fact(symptom_id, False)
                break
            elif answer == "?":
                fb.mark_unknown(symptom_id)
                break
            else:
                print("  → Répondez O, N ou ?")

        count += 1

        # Arrêt anticipé si min atteint ET diagnostic très confiant
        if fb.count_all_answers() >= MIN_ANSWERS:
            try:
                current_diagnoses = engine.run(fb)
                if current_diagnoses and current_diagnoses[0]["confidence"] > 0.9:
                    print("\n⚡ Diagnostic de haute confiance trouvé, arrêt des questions.\n")
                    break
            except ValueError:
                pass

    # Résultats finaux
    print("\n" + "="*60)
    print("  RÉSULTATS DU DIAGNOSTIC")
    print("="*60)

    try:
        diagnoses = engine.run(fb)
    except ValueError as e:
        print(f"\n❌ {e}")
        print("="*60)
        return

    if not diagnoses:
        print("\n❌ Aucun diagnostic ne correspond aux symptômes fournis.")
        print("   Essayez de répondre à plus de questions ou consultez un technicien.")
    else:
        print(f"\n✅ {len(diagnoses)} diagnostic(s) identifié(s) (max {MAX_DIAGNOSES}) :\n")
        for i, d in enumerate(diagnoses, 1):
            print(f"{'─'*50}")
            print(f"Diagnostic #{i} — Confiance : {int(d['confidence']*100)}%")
            print(engine.explain(d, fb))

    print("\n" + "="*60)


if __name__ == "__main__":
    run_cli_session()
