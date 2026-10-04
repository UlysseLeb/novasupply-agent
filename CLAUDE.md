# NovaSupply Ops Agent — conventions du projet

Réécriture agentique de [[novasupply-inbox-ai]] : reprend le même problème (triage et réponse aux emails de support NovaSupply) mais laisse le modèle décider lui-même quels outils appeler — commande réelle via HubSpot, procédures internes via Bedrock Knowledge Base, escalade humaine via un Ticket HubSpot — au lieu du routage `if/else` figé du pipeline n8n existant. Projet d'apprentissage agentic engineering + cloud AWS (Strands Agents, Bedrock, Lambda, CDK). Scaffoldé le 2026-10-03 sous le nom provisoire "Meridian Ops Agent", réorienté le même jour vers ce cas réel.

Voir le brief complet : `docs/PROJECT.md`.

## Conventions

- Commentaires et docstrings en français, code (noms de variables/fonctions) en anglais — même convention que les autres projets freelance-clients.
- Avancer phase par phase (voir roadmap dans `docs/PROJECT.md`) : ne pas déployer sur AWS avant que l'agent local (Phase 0) ait validé son choix autonome d'outils sur plusieurs cas de test.
- Infra définie en CDK (Python), jamais de ressource créée à la main dans la console AWS une fois la Phase 1 commencée.
- Auth API par header `X-API-Key`, même patron que pme-rag-chatbot et novasupply-inbox-ai.
- Ne pas committer `.env`, `cdk.out/`, ni aucune donnée de coûts/facturation réelle.
- Ne pas modifier le projet `novasupply-inbox-ai` existant (pipeline n8n en prod) : celui-ci est une réécriture séparée, pas une migration en place.
