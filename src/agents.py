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
    model = BedrockModel(
        model_id="eu.anthropic.claude-haiku-4-5-20251001-v1:0",
        region_name="eu-west-3",
    )

    return Agent(
        model=model,
        tools=[get_order_context, search_policy, escalate_to_human],
        system_prompt=SYSTEM_PROMPT,
    )