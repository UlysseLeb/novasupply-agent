"""Cas de test manuels pour valider le choix autonome d'outils de l'agent (Phase 0).

Objectif : vérifier que l'agent choisit seul la bonne séquence d'outils selon
le message, sans qu'aucune règle if/else ne lui dicte le chemin à l'avance.
"""

import os

# Charge .env à la racine du projet (pas de dépendance python-dotenv pour ça,
# un simple fichier KEY=VALUE suffit pour cet unique secret local).
_ENV_PATH = os.path.join(os.path.dirname(__file__), "..", ".env")
if os.path.exists(_ENV_PATH):
    with open(_ENV_PATH) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key, value)

from agents import create_agent

TEST_CASES = [
    {
        "nom": "Signal secondaire noyé",
        "message": (
            "Bonjour, je voulais réinitialiser mon mot de passe sur le portail. "
            "Au fait, ma commande CMD-4006 est arrivée avec des pièces manquantes, "
            "c'est la troisième fois en deux mois."
        ),
        # Attendu : l'agent doit repérer la plainte malgré la question anodine en tête de message,
        # appeler get_order_context pour vérifier l'écart réel, puis escalader.
        # CMD-4006 est un vrai Deal HubSpot (10x CAP-100 commandés, 7 expédiés dans la table fulfillments).
    },
    {
        "nom": "Question simple sans signal caché",
        "message": "Quel est le délai pour faire une réclamation sur une commande ?",
        # Attendu : l'agent doit répondre directement via search_policy, sans
        # appeler get_order_context ni escalate_to_human (rien ne justifie une escalade ici).
    },
    {
        "nom": "Commande conforme, pas d'écart",
        "message": "Bonjour, pouvez-vous me confirmer que la commande CMD-4006 a bien été expédiée complète ?",
        # Attendu : l'agent appelle get_order_context, voit l'écart réel (HubSpot + DynamoDB réels)
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
