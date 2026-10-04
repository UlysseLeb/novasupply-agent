"""Outils de l'agent NovaSupply Ops.

Phase 1 : get_order_context et escalate_to_human appellent le vrai HubSpot
(même modèle de données que novasupply-inbox-ai) et la vraie table DynamoDB
`fulfillments`. search_policy reste mocké jusqu'à la vraie Knowledge Base
Bedrock (Phase 2). Les docstrings ci-dessous sont lues par le décorateur
@tool pour générer la description que le modèle voit : elles doivent rester
précises, c'est ce qui guide le choix de l'agent.
"""

import boto3

# `tool` est le décorateur fourni par Strands. C'est lui qui transforme une
# fonction Python normale en "outil" que l'agent peut voir et choisir d'appeler.
from strands import tool

import hubspot_client

FULFILLMENTS_TABLE_NAME = "novasupply-agent-fulfillments"
_dynamodb = boto3.resource("dynamodb", region_name="eu-west-3")


# Le décorateur @tool va lire deux choses sur cette fonction pour construire
# la fiche que le modèle voit : son nom (`get_order_context`), les types des
# paramètres (`order_ref: str`), et surtout sa docstring. C'est la docstring,
# pas un commentaire `#`, qui sert de description à l'outil, car elle reste
# accessible à l'exécution (via `__doc__`) alors qu'un `#` disparaît à la lecture.
@tool
def get_order_context(order_ref: str) -> str:
    """Récupère les line items commandés (HubSpot) et les fulfillments réels (DynamoDB) pour une commande.

    Ne compare pas elle-même les deux : elle fournit les données brutes,
    c'est à l'agent de repérer un éventuel écart et de décider quoi en faire.
    (Choix volontaire : si cette fonction comparait elle-même, on retomberait
    dans le routage if/else figé qu'on cherche justement à remplacer.)

    Args:
        order_ref: Référence de la commande (ex: "CMD-4006")
    """
    # Le dealname HubSpot EST la référence de commande (pas de propriété séparée) :
    # même modèle que novasupply-inbox-ai, pour ne pas dupliquer de donnée.
    deal = hubspot_client.find_deal_by_order_ref(order_ref)
    if deal is None:
        return f"Aucune commande trouvée pour la référence '{order_ref}'."

    ordered_items = hubspot_client.get_ordered_line_items(deal["id"])

    # Ce qui a réellement été expédié ne vient jamais de HubSpot (un CRM ne sait
    # pas ce qui est sorti de l'entrepôt) : donnée simulée dans DynamoDB,
    # NovaSupply n'ayant pas de vrai système d'entrepôt.
    table = _dynamodb.Table(FULFILLMENTS_TABLE_NAME)
    fulfillment = table.get_item(Key={"order_ref": order_ref}).get("Item")
    shipped_items = fulfillment["shipped_products"] if fulfillment else []

    # On renvoie du texte brut (pas un objet structuré) car c'est ce que Strands
    # attend en sortie d'outil : un texte que le modèle va lire et interpréter lui-même.
    return (
        f"Commande {order_ref}\n"
        f"Commandé (HubSpot) : {ordered_items}\n"
        f"Expédié (DynamoDB fulfillments) : {shipped_items}"
    )


@tool
def search_policy(query: str) -> str:
    """Cherche une politique interne (remboursement, délai de réclamation, etc.) correspondant à une requête en langage naturel.

    Indépendant de toute commande précise : la même règle vaut pour tous les clients
    (contrairement à get_order_context, qui lui dépend d'une commande donnée).
    Phase 0 : correspondance par mot-clé sur un petit jeu de politiques en dur,
    en attendant la vraie Knowledge Base Bedrock (Phase 2).

    Args:
        query: Question ou sujet recherché (ex: "quel est le délai de réclamation ?")
    """
    # .lower() neutralise la casse (majuscule/minuscule) mais pas les accents :
    # "É" et "é" deviennent identiques, mais "é" et "e" restent deux caractères
    # différents pour Python. Le mot-clé cherché doit donc garder son accent
    # pour matcher une vraie phrase française (ex: "réclamation", pas "reclamation").
    query_lower = query.lower()

    # `in` vérifie une sous-chaîne, pas une égalité exacte : ça permet de retrouver
    # le mot-clé peu importe comment la phrase est tournée autour de lui.
    if "réclamation" in query_lower:
        return "Délai de réclamation : 3 semaines après réception de la commande."
    if "remboursement" in query_lower:
        return "Politique de remboursement : remboursement intégral sous 1 semaine si le produit est défectueux."

    # Filet de sécurité : si aucun mot-clé ne matche, on le dit explicitement
    # plutôt que de renvoyer None ou une erreur, pour que l'agent sache quoi faire de cette absence.
    return "Aucune politique interne trouvée pour cette requête."


@tool
def escalate_to_human(reason: str, order_ref: str) -> str:
    """Escalade une question ou un problème à un humain.

    Crée un vrai Ticket HubSpot (Service Hub) plutôt qu'une table DynamoDB
    dédiée : HubSpot a déjà un objet fait pour ça.

    Args:
        reason: La raison de l'escalade (ex: "écart de quantité répété").
        order_ref: La référence de la commande concernée.
    """
    # C'est l'agent qui décide QUAND appeler cette fonction (ex: après avoir vu
    # un écart via get_order_context), pas une règle if/else écrite à l'avance.
    ticket_id = hubspot_client.create_ticket(
        subject=f"Escalade commande {order_ref}",
        content=reason,
    )
    return f"Ticket HubSpot {ticket_id} créé pour la commande {order_ref} : {reason}"
