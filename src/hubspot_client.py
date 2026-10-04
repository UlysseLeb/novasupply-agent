"""Petit client HubSpot minimaliste (stdlib uniquement, pas de dépendance `requests`).

Reprend le même modèle de données que novasupply-inbox-ai (projet existant,
pipeline n8n en prod) : le numéro de commande est le `dealname` du Deal, et
la référence produit est encodée à la fin du nom du line item (le champ
hs_sku n'est pas rempli sur les données de démo).
"""

import json
import os
import re
import urllib.error
import urllib.request

HUBSPOT_API_BASE = "https://api.hubapi.com"

# Référence produit à la fin du nom (ex: "Casques de chantier CAP-100" -> "CAP-100").
_REFERENCE_PATTERN = re.compile(r"[A-Z]+-\d+$")


def _request(method: str, path: str, body: dict | None = None) -> dict | None:
    token = os.environ["HUBSPOT_PRIVATE_APP_TOKEN"]
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"{HUBSPOT_API_BASE}{path}",
        data=data,
        method=method,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        # Un Deal/Contact manquant n'est pas une panne réseau, juste une absence
        # de résultat : on la laisse remonter comme "pas trouvé" côté appelant.
        if e.code == 404:
            return None
        raise


def find_deal_by_order_ref(order_ref: str) -> dict | None:
    """Cherche le Deal dont le dealname correspond exactement à la référence de commande."""
    result = _request(
        "POST",
        "/crm/v3/objects/deals/search",
        {
            "filterGroups": [{"filters": [{"propertyName": "dealname", "operator": "EQ", "value": order_ref}]}],
            "properties": ["dealname"],
        },
    )
    results = (result or {}).get("results", [])
    return results[0] if results else None


def get_ordered_line_items(deal_id: str) -> list[dict]:
    """Récupère les line items associés à un Deal, avec référence extraite et quantité commandée."""
    deal = _request("GET", f"/crm/v3/objects/deals/{deal_id}?associations=line_items")
    if deal is None:
        return []

    associations = deal.get("associations", {}).get("line items", {}).get("results", [])
    line_items = []
    for assoc in associations:
        item = _request("GET", f"/crm/v3/objects/line_items/{assoc['id']}?properties=name,quantity")
        if item is None:
            continue
        name = item["properties"]["name"]
        reference = _REFERENCE_PATTERN.search(name)
        line_items.append(
            {
                "reference": reference.group() if reference else name,
                "quantity_ordered": int(item["properties"]["quantity"]),
            }
        )
    return line_items


def create_ticket(subject: str, content: str) -> str:
    """Crée un Ticket HubSpot (Service Hub). Pipeline/stage par défaut du portail (0/1)."""
    result = _request(
        "POST",
        "/crm/v3/objects/tickets",
        {
            "properties": {
                "subject": subject,
                "content": content,
                "hs_pipeline": "0",
                "hs_pipeline_stage": "1",
            }
        },
    )
    return result["id"]
