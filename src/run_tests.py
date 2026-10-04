"""Cas de test manuels pour valider le choix autonome d'outils de l'agent (Phase 0).

Objectif : vérifier que l'agent choisit seul la bonne séquence d'outils selon
le message, sans qu'aucune règle if/else ne lui dicte le chemin à l'avance.
"""

from agents import create_agent

TEST_CASES = [
    {
        "nom": "Signal secondaire noyé",
        "message": (
            "Bonjour, je voulais réinitialiser mon mot de passe sur le portail. "
            "Au fait, ma commande ORD-1042 est arrivée avec des pièces manquantes, "
            "c'est la troisième fois en deux mois."
        ),
        # Attendu : l'agent doit repérer la plainte malgré la question anodine en tête de message,
        # appeler get_order_context pour vérifier l'écart réel, puis escalader.
    },
    {
        "nom": "Question simple sans signal caché",
        "message": "Quel est le délai pour faire une réclamation sur une commande ?",
        # Attendu : l'agent doit répondre directement via search_policy, sans
        # appeler get_order_context ni escalate_to_human (rien ne justifie une escalade ici).
    },
    {
        "nom": "Commande conforme, pas d'écart",
        "message": "Bonjour, pouvez-vous me confirmer que la commande ORD-1042 a bien été expédiée complète ?",
        # Attendu : l'agent appelle get_order_context, voit l'écart réel dans le mock
        # (ce cas sert surtout à vérifier qu'il ne sur-réagit pas s'il n'y a PAS de plainte formulée).
    },
]


def main() -> None:
    for case in TEST_CASES:
        print(f"\n{'=' * 60}\nCas : {case['nom']}\n{'=' * 60}")
        agent = create_agent()  # instance neuve : pas d'historique entre les cas
        agent(case["message"])


if __name__ == "__main__":
    main()
