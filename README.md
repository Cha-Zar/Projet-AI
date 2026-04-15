Rapport — Système Expert SysDiag
🔹 1. Architecture

Le système est basé sur :

Base de faits (FactBase)
Base de connaissances (règles)
Moteur d’inférence (chaînage avant)
🔹 2. Fonctionnement
L’utilisateur répond aux questions
Les réponses alimentent la base de faits
Le moteur :
filtre les questions
sélectionne la plus pertinente
Après seuil minimal → diagnostic
🔹 3. Améliorations apportées
✅ Filtrage contextuel

Le système ne pose que des questions cohérentes avec le contexte.

✅ Détection des contradictions

Ex :

PC ne démarre pas ❌ vs fonctionne ✔
✅ Priorisation intelligente

Questions choisies selon :

règles impactées
position dans l’arbre
✅ Score de confiance dynamique

Basé sur :

conditions vérifiées
incertitudes
🔹 4. Algorithme utilisé
Parcours BFS restreint
Scoring heuristique
Chaînage avant
🔹 5. Résultat

✔ Diagnostic plus rapide
✔ Moins de questions inutiles
✔ Cohérence logique
✔ Explicable (important en IA)

🔥 CONCLUSION

👉 Avant :

questions aléatoires ❌
contradictions ❌

👉 Maintenant :

système intelligent ✔
cohérent ✔
niveau académique ✔
