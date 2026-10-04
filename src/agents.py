from strands import Agent
from strands.models import BedrockModel
from tools import get_order_context, search_policy, escalate_to_human

SYSTEM_PROMPT = "Tu es un agent qui répond au client. Utilise get_order_context pour obtenir le contexte d'une commande, search_policy pour rechercher les politiques, et escalate_to_human pour rediriger vers un humain. SI tu détectes une situation qui nécessite une intervention humaine (plainte ou autre), utilise escalate_to_human."  # à toi d'écrire : le rôle de l'agent, et quand utiliser chaque outil

def create_agent() -> Agent:
    """Construit un agent neuf, sans historique de conversation.

    Une fonction plutôt qu'un objet au niveau module : un `Agent` Strands garde
    l'historique des messages entre les appels. Réutiliser la même instance
    pour plusieurs cas de test indépendants ferait fuiter le contexte de l'un
    vers l'autre (ex: un cas qui "se souvient" d'une commande mentionnée dans
    un cas précédent sans que le message actuel n'en parle).
    """
    # Modèle explicite : Haiku 4.5 (le moins cher côté Claude) via le profil
    # d'inférence EU (eu-west-3), plutôt que le défaut Strands (Sonnet, us-west-2).
    # guardrail_id/version : filtre appliqué par Bedrock lui-même sur l'entrée
    # ET la sortie du modèle (Phase 3), indépendant du system_prompt — un
    # garde-fou mécanique plutôt qu'une simple instruction que le modèle
    # pourrait oublier sur un cas limite (ex: menace légale).
    model = BedrockModel(
        model_id="eu.anthropic.claude-haiku-4-5-20251001-v1:0",
        region_name="eu-west-3",
        guardrail_id="v406mt0akphs",
        guardrail_version="DRAFT",
        guardrail_trace="enabled",
    )

    return Agent(
        model=model,
        tools=[get_order_context, search_policy, escalate_to_human],
        system_prompt=SYSTEM_PROMPT,
    )


def tools_called(agent: Agent) -> list[str]:
    """Extrait les noms d'outils appelés depuis l'historique de la conversation.

    Utilisé par evals.py (vérifier le comportement) et lambda_handler.py
    (enregistrer la trace de la décision) : un seul endroit pour lire la
    structure interne des messages Strands plutôt que la dupliquer.
    """
    return [
        block["toolUse"]["name"]
        for message in agent.messages
        for block in message.get("content", [])
        if "toolUse" in block
    ]