# NovaSupply Ops Agent

Un agent IA qui traite les emails de support d'un distributeur B2B fictif (NovaSupply), en décidant lui-même quels outils appeler et dans quel ordre — au lieu d'un routage `if/else` figé sur une seule classification.

## Le problème

[novasupply-inbox-ai](https://github.com/UlysseLeb/novasupply-inbox-ai) est un pipeline existant (n8n) qui classe chaque email puis applique une règle de routage fixe. Limite : la règle ne regarde que la sortie de classification, jamais le contenu complet de l'email une seconde fois. Un signal secondaire noyé dans un message par ailleurs simple n'est jamais traité :

> « Comment je fais pour réinitialiser mon mot de passe sur le portail commande ? Au fait, c'est la troisième fois en deux mois que ma commande arrive avec des pièces manquantes, à ce rythme je vais regarder ailleurs. »

Une règle `if/else` classerait ce message « simple ». Un agent qui lit le message en entier peut remarquer la plainte, vérifier l'historique réel du client, et décider seul s'il faut escalader.

## Ce que fait l'agent

Trois outils, décrits au modèle via leur docstring (lue par le décorateur `@tool` de [Strands Agents](https://github.com/strands-agents/sdk-python)) :

| Outil | Rôle | Source |
|---|---|---|
| `get_order_context(order_ref)` | Ramène ce qui a été commandé et ce qui a réellement été expédié — sans comparer lui-même, c'est à l'agent de repérer un écart | HubSpot (Deal → line items) + DynamoDB `fulfillments` |
| `search_policy(query)` | Recherche sémantique sur les procédures internes (remboursement, délai de réclamation, menace légale) — retrouve un synonyme sans liste de mots-clés écrite à la main | Bedrock Knowledge Base (S3 Vectors) |
| `escalate_to_human(reason, order_ref)` | Transfère le dossier à un humain | Ticket HubSpot (Service Hub) |

Aucun orchestrateur custom ne décide quel outil appeler : c'est le modèle (Claude Haiku 4.5 via Amazon Bedrock) qui choisit, à partir de sa description et du message reçu.

## Exemple réel

Testé sur une vraie commande HubSpot (`CMD-4006`, 10 unités de CAP-100 commandées, 7 expédiées) :

```
→ "Je voulais réinitialiser mon mot de passe. Au fait, ma commande CMD-4006
   est arrivée avec des pièces manquantes, la troisième fois en deux mois."

← L'agent appelle get_order_context, trouve l'écart réel (3 unités manquantes),
  puis escalate_to_human → crée un vrai Ticket HubSpot (#436294178012).
```

## Garde-fous

- **Guardrail Bedrock** : bloque toute réponse qui ressemblerait à un conseil juridique ou une reconnaissance de responsabilité (testé par injection de prompt adversariale, pas juste un message normal), et anonymise les données personnelles (email, téléphone) dans les réponses.
- **Suite d'évaluation** (`src/evals.py`) : vérifie par assertion quels outils l'agent a réellement appelés pour chaque cas, pas une relecture humaine du texte. 5/5 cas passent, dont un garde-fou anti-sur-déclenchement (une question hors périmètre ne doit appeler aucun outil).
- **Observabilité** : chaque requête écrit une trace (outils appelés, décision finale, latence) dans une table DynamoDB.

## Stack

Python · [Strands Agents](https://github.com/strands-agents/sdk-python) · Amazon Bedrock (Claude Haiku 4.5, Titan Embeddings, Knowledge Base, Guardrails) · AWS Lambda + API Gateway (HTTP API) · DynamoDB · S3 Vectors · HubSpot API · AWS CDK (Python)

**S3 Vectors plutôt qu'OpenSearch Serverless** pour le vector store de la Knowledge Base : OpenSearch Serverless facture un minimum fixe même à l'arrêt (~300-700$/mois), S3 Vectors (sorti en décembre 2025) est payé à l'usage, sans infrastructure à gérer.

## Architecture

Schéma de l'infrastructure réelle par phase (pas le plan initial, ce qui tourne vraiment) : [voir l'artefact](https://claude.ai/artifact/JmC1Jk61bKFFhz43yuGBqP).

## Statut

Les 4 phases prévues sont construites et validées de bout en bout (local + déploiement réel) :

- **Phase 0** — prototype local, 3 outils stubbés, validation du choix autonome d'outils.
- **Phase 1** — déploiement Lambda + API Gateway via CDK, connexion HubSpot réelle.
- **Phase 2** — RAG réel sur Bedrock Knowledge Base (S3 Vectors).
- **Phase 3** — Guardrail Bedrock + observabilité (table `traces`).

Détail complet des décisions et des bugs rencontrés dans [`docs/PROJECT.md`](docs/PROJECT.md).

## Lancer en local

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
# .env à la racine avec HUBSPOT_PRIVATE_APP_TOKEN=...
cd src && python3 run_tests.py   # démo lisible
python3 evals.py                 # suite d'évaluation automatisée
```

## Déployer

```bash
cd infra
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cdk bootstrap && cdk deploy
# puis déclencher l'ingestion de la Knowledge Base (CloudFormation ne le fait pas) :
aws bedrock-agent start-ingestion-job --knowledge-base-id <id> --data-source-id <id>
```

## Limites connues

- Permissions IAM volontairement larges pour ce prototype perso (plusieurs policies `*FullAccess`), à resserrer avant tout usage pour un vrai client.
- Un écart de commande détecté sans plainte explicite du client déclenche quand même une escalade — comportement pas encore tranché, documenté dans `docs/PROJECT.md`.
