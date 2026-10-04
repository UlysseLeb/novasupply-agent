"""Suite d'évaluation automatisée de l'agent.

Contrairement à run_tests.py (lecture humaine du texte de réponse), ce
fichier vérifie par assertion QUELS outils l'agent a réellement appelés
pour chaque cas, et échoue bruyamment si le comportement dérive. C'est ce
qui permet de détecter une régression sans relire la réponse à chaque fois.
"""

import os
from dataclasses import dataclass, field

_ENV_PATH = os.path.join(os.path.dirname(__file__), "..", ".env")
if os.path.exists(_ENV_PATH):
    with open(_ENV_PATH) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key, value)

from agents import create_agent


@dataclass
class EvalCase:
    name: str
    message: str
    # Outils qui DOIVENT avoir été appelés pour que le cas soit un succès.
    must_call: set[str] = field(default_factory=set)
    # Outils qui ne doivent PAS avoir été appelés (sur-déclenchement à éviter).
    must_not_call: set[str] = field(default_factory=set)
    # Si True, le cas est affiché mais ne compte pas dans le score : utile
    # pour un comportement volontairement ouvert (ex: escalade sans plainte
    # explicite, cf. point de design noté dans PROJECT.md).
    informational: bool = False


CASES = [
    EvalCase(
        name="Signal secondaire noyé",
        message=(
            "Bonjour, je voulais réinitialiser mon mot de passe sur le portail. "
            "Au fait, ma commande CMD-4006 est arrivée avec des pièces manquantes, "
            "c'est la troisième fois en deux mois."
        ),
        must_call={"get_order_context", "escalate_to_human"},
    ),
    EvalCase(
        name="Question de politique sans signal caché",
        message="Quel est le délai pour faire une réclamation sur une commande ?",
        must_call={"search_policy"},
        must_not_call={"get_order_context", "escalate_to_human"},
    ),
    EvalCase(
        name="Question hors périmètre (pas d'outil pertinent)",
        message="Quelle est la capitale de la France ?",
        must_not_call={"get_order_context", "search_policy", "escalate_to_human"},
    ),
    EvalCase(
        name="Commande en écart mais sans plainte explicite",
        message="Bonjour, pouvez-vous me confirmer que la commande CMD-4006 a bien été expédiée complète ?",
        must_call={"get_order_context"},
        informational=True,  # escalade ou pas : comportement pas encore tranché (Phase 3)
    ),
]


def tools_called(agent) -> list[str]:
    """Extrait les noms d'outils appelés depuis l'historique de la conversation."""
    return [
        block["toolUse"]["name"]
        for message in agent.messages
        for block in message.get("content", [])
        if "toolUse" in block
    ]


def run_case(case: EvalCase) -> bool:
    agent = create_agent()
    agent(case.message)  # la sortie texte streamée par Strands reste visible dans le terminal
    called = set(tools_called(agent))

    missing = case.must_call - called
    unexpected = called & case.must_not_call

    print(f"\n{'=' * 60}\n{case.name}\nOutils appelés : {sorted(called)}")

    if case.informational:
        print("(informationnel, hors score)")
        return True

    if missing or unexpected:
        if missing:
            print(f"ÉCHEC — outils attendus manquants : {sorted(missing)}")
        if unexpected:
            print(f"ÉCHEC — outils inattendus appelés : {sorted(unexpected)}")
        return False

    print("OK")
    return True


def main() -> None:
    results = [run_case(case) for case in CASES]
    scored = [r for c, r in zip(CASES, results) if not c.informational]
    passed = sum(scored)
    print(f"\n{'=' * 60}\n{passed}/{len(scored)} cas notés réussis ({len(results) - len(scored)} informationnel(s))")
    if passed < len(scored):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
