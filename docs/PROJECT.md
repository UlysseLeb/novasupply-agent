# NovaSupply Ops Agent

Projet d'apprentissage agentic engineering + cloud AWS. Objectif : transformer [[novasupply-inbox-ai]], aujourd'hui un pipeline déterministe (n8n + règle de routage en dur), en un vrai agent (boucle d'outils, décision autonome du modèle) déployé sur infrastructure AWS serverless réelle, avec l'infra définie en code (CDK).

Point de départ : entretien technique Seven Mile (2026-09-29/30, AWS/GenAI/agents) où il est apparu qu'aucun agent réel n'avait encore été construit — seulement des pipelines déterministes ([[novasupply-inbox-ai]]) ou du RAG classique ([[pme-rag-chatbot]]). Scaffoldé une première fois le 2026-10-03 sous un nom de client fictif inventé pour l'occasion ("Meridian Ops Agent", transport B2B), puis réorienté le même jour vers un cas déjà connu et déjà construit : NovaSupply.

## Contexte : NovaSupply Inbox AI

[[novasupply-inbox-ai]] est un produit perso existant (démo/portfolio) : triage et rédaction de réponses aux emails de support pour NovaSupply, un distributeur B2B fictif de composants industriels (capteurs, vannes, modules de contrôle). Le pipeline actuel classe chaque email (niveau de complexité, sentiment), puis une règle déterministe décide quoi faire : réponse automatique, brouillon à valider par un humain, ou transfert direct. Deux sources de données, chacune dans son rôle naturel : **HubSpot** (CRM réel, ce que le client a commandé) et `orders.json` (donnée simulée jouant le rôle de l'entrepôt/ERP que NovaSupply n'a pas, ce qui a réellement été expédié).

Limite de ce pipeline, et raison d'être de ce projet : le routage ne regarde que la sortie de classification, jamais le contenu complet de l'email une seconde fois. Un signal important noyé dans un message par ailleurs "simple" (ex: une plainte récurrente glissée après une question anodine sur un mot de passe) n'est jamais traité, parce que rien dans la règle `if/else` ne l'a prévu.

## Ce que l'agent doit faire

Reprendre le même problème métier que [[novasupply-inbox-ai]], mais laisser le modèle décider lui-même quels outils appeler et dans quel ordre, au lieu d'un routage figé qui ne regarde qu'un seul niveau de classification. Exemple de requête test :

> "Comment je fais pour réinitialiser mon mot de passe sur le portail commande ? Au fait, c'est la troisième fois en deux mois que ma commande arrive avec des pièces manquantes, à ce rythme je vais regarder ailleurs."

Un agent correct doit pouvoir répondre à la question simple tout en remarquant le signal secondaire (écarts de commande répétés), vérifier l'historique réel du client, consulter la procédure interne correspondante, et décider seul s'il faut escalader — sans qu'aucune règle n'ait câblé ce cas précis à l'avance.

## Outils de l'agent (3)

1. **`get_order_context(order_ref)`** — combine un appel HubSpot (Contact → Deal → line items, ce que le client a commandé) et un lookup DynamoDB (table `fulfillments`, ce qui a réellement été expédié — donnée simulée, NovaSupply n'a pas de vrai système d'entrepôt, même rôle que `shipments` dans la version initiale du projet). Pas de duplication : HubSpot reste la source de vérité pour la commande, DynamoDB ne porte que ce qui n'existe nulle part ailleurs.
2. **`search_policy(query)`** — RAG via Bedrock Knowledge Base sur une poignée de documents internes (politique de remboursement, délai de réclamation, seuil à partir duquel un geste commercial nécessite une validation humaine, procédure pour une menace légale), stockés en S3. Corpus volontairement petit (3-4 pages) : monter une vraie Knowledge Base ici n'est pas nécessaire techniquement, c'est un choix assumé pour pratiquer la stack AWS.
3. **`escalate_to_human(reason, order_ref)`** — crée un Ticket dans HubSpot plutôt que d'écrire dans une table DynamoDB dédiée : HubSpot a déjà un objet fait pour ça (Service Hub), pas de raison de dupliquer un système que l'équipe utilise déjà au quotidien.

Aucun orchestrateur custom ne décide quel outil appeler : c'est le framework agentique + le modèle qui choisissent, à partir du prompt système et de la description de chaque outil.

## Stack technique retenue

- **Python 3.12**
- **Strands Agents** (framework agentique open source d'AWS) pour la boucle de l'agent — choisi plutôt que LangGraph pour rester au plus près de la stack AWS native visée par l'entretien ; LangGraph reste à connaître en complément, plus portable hors AWS.
- **Amazon Bedrock** comme fournisseur de modèle (Claude via Bedrock) — pas d'appel direct à l'API Anthropic, pour pratiquer la gouvernance modèle côté AWS (accès scopé par IAM, logging, guardrails).
- **AWS Lambda** pour héberger l'agent (handler Python), derrière **API Gateway** (HTTP API), avec une clé API (`X-API-Key`) — même patron d'auth que [[pme-rag-chatbot]] et [[novasupply-inbox-ai]].
- **HubSpot** comme source de vérité pour les commandes (lecture) et les escalades (écriture d'un Ticket) — appelé directement depuis Lambda, pas de copie dans DynamoDB.
- **DynamoDB** pour `fulfillments` (donnée simulée d'expédition, inexistante ailleurs) et `traces` (tracabilité de l'agent) — ni les commandes ni les escalades n'y vont, elles restent dans HubSpot.
- **S3 + Bedrock Knowledge Base** pour le RAG sur les procédures internes.
- **AWS CDK (Python)** pour toute l'infra, versionnée dans ce repo.
- **CloudWatch Logs** + la table DynamoDB `traces` pour la tracabilité (outils appelés, décision finale, latence) — adaptation du réflexe de tracing JSONL utilisé sur [[pme-rag-chatbot]]/projet-RAG, mais une Lambda n'a pas de disque persistant, donc le pattern change : log structuré + table dédiée plutôt que fichier local.

## Point de vigilance coût

Pas d'abonnement, tout est pay-per-use (Bedrock au token, Lambda/DynamoDB avec palier gratuit généreux, CDK gratuit). Le seul piège identifié : **OpenSearch Serverless** (souvent le store vectoriel par défaut pour une Knowledge Base Bedrock) facture même à l'arrêt, hors palier gratuit. À vérifier au moment de construire la Knowledge Base si une alternative moins chère est disponible dans la région visée (ex. S3 Vectors, plus récent, pay-per-use) — à re-checker dans la console AWS au moment de builder, les offres évoluent vite. Poser une alerte de budget AWS dès la création du compte, avant toute ressource.

## Roadmap par phases

**Phase 0 — prototype local (coût quasi nul)**
Agent Strands qui tourne en local, appelle Bedrock via `boto3`, outils = fonctions Python qui retournent des données mockées en dur (pas encore d'appel HubSpot réel ni d'AWS réel derrière). But : valider que le modèle choisit seul la bonne séquence d'outils sur plusieurs cas de test (dont le cas "signal secondaire noyé" ci-dessus), avant de dépenser le moindre euro d'infra.

**Phase 1 — déploiement serverless**
Même agent, packagé en handler Lambda, déployé via CDK, exposé par API Gateway + clé API. Connexion réelle à HubSpot (lecture Contact/Deal/line items, écriture de Ticket). Table DynamoDB `fulfillments` seedée avec les mêmes données mockées que la Phase 0.

**Phase 2 — RAG réel**
Création de la Bedrock Knowledge Base sur de vrais documents de procédure (courts, écrits pour l'occasion), remplacement du stub `search_policy` par une vraie requête RAG.

**Phase 3 — guardrails et observabilité**
Ajout d'un Bedrock Guardrail (filtrage de sujets, détection PII en démo), structuration de la table `traces`, alerte de budget.

## Statut

Scaffold créé le 2026-10-03 sous le nom provisoire "Meridian Ops Agent" (client fictif inventé pour l'occasion), réorienté le même jour vers NovaSupply après une session de conception (dossier renommé `novasupply-agent`).

**Phase 0 validée le 2026-10-04** : 3 outils stubbés (`src/tools.py`), agent Strands connecté à Claude Haiku 4.5 via Bedrock (profil d'inférence EU, région `eu-west-3`), testé sur 3 cas (`src/run_tests.py`). Résultat sur le cas test de référence (signal secondaire noyé dans une question anodine) : l'agent repère la plainte récurrente malgré la question sur le mot de passe, appelle `get_order_context`, trouve l'écart réel (2 capteurs manquants), et appelle `escalate_to_human`, sans aucune règle `if/else` écrite pour ce cas précis. Un cas test sans plainte explicite montre que l'agent escalade dès qu'il détecte un écart réel, même non signalé par le client : point de design à retrancher en Phase 3 (faut-il réserver l'escalade aux cas où le client exprime une insatisfaction ?).

Compte AWS créé le 2026-10-04 : utilisateur IAM dédié `novasupply-agent-local` (`AmazonBedrockFullAccess`, clés d'accès locales via `aws configure`, jamais commitées), budget zero-spend configuré avant toute ressource.

Prochaine étape : Phase 1, packaging Lambda + CDK + connexion HubSpot réelle.

## Liens

- Déclencheur : entretien Seven Mile — voir [[novasupply-inbox-ai]] (section préparation entretien) pour le contexte complet.
- Projet d'origine dont celui-ci reprend le problème métier : [[novasupply-inbox-ai]] (`~/Desktop/CODE/produits-perso/novasupply-inbox-ai/`). Le pipeline n8n déterministe qui y tourne reste en place et inchangé — ce projet-ci est une réécriture agentique séparée, pas une migration en place du produit existant.
- Projet voisin resté en pause pour la même raison stratégique : `~/Desktop/CODE/freelance-clients/projet-RAG/` (agent RAG sur doc n8n, scaffoldé puis mis en pause le 2026-09-29).
