# NovaSupply Ops Agent

An AI agent that handles support emails for a fictional B2B distributor (NovaSupply), deciding on its own which tools to call and in what order, instead of a fixed `if/else` route built on a single classification.

## The problem

[novasupply-inbox-ai](https://github.com/UlysseLeb/novasupply-inbox-ai) is an existing pipeline (n8n) that classifies each email and then applies a fixed routing rule. Its limit: the rule only ever looks at the classification output, never the email's full content a second time. A secondary signal buried inside an otherwise simple message never gets handled:

> "How do I reset my password on the order portal? By the way, this is the third time in two months my order arrives with missing parts, at this rate I'm going to look elsewhere."

An `if/else` rule would classify this message as "simple". An agent that reads the whole message can notice the complaint, check the customer's actual history, and decide on its own whether to escalate.

## What the agent does

Three tools, described to the model through their docstring (read by [Strands Agents](https://github.com/strands-agents/sdk-python)'s `@tool` decorator):

| Tool | Role | Source |
|---|---|---|
| `get_order_context(order_ref)` | Returns what was ordered and what was actually shipped, without comparing them itself, it's up to the agent to spot a discrepancy | HubSpot (Deal → line items) + DynamoDB `fulfillments` |
| `search_policy(query)` | Semantic search over internal procedures (refunds, claim deadlines, legal threats), finds a synonym without a hand-written keyword list | Bedrock Knowledge Base (S3 Vectors) |
| `escalate_to_human(reason, order_ref)` | Hands the case off to a human | HubSpot Ticket (Service Hub) |

No custom orchestrator decides which tool to call: the model (Claude Haiku 4.5 via Amazon Bedrock) chooses, based on its description and the message it receives.

## Real example

Tested on a real HubSpot order (`CMD-4006`, 10 units of CAP-100 ordered, 7 shipped):

```
→ "I wanted to reset my password. By the way, my order CMD-4006
   arrived with missing parts, the third time in two months."

← The agent calls get_order_context, finds the real discrepancy (3 missing
  units), then escalate_to_human → creates a real HubSpot Ticket (#436294178012).
```

## Guardrails

- **Bedrock Guardrail**: blocks any response that resembles legal advice or an admission of liability (tested through adversarial prompt injection, not just a normal message), and anonymizes personal data (email, phone) in responses.
- **Eval suite** (`src/evals.py`): checks by assertion which tools the agent actually called for each case, not a human reading the text. 5/5 cases pass, including a guard against over-triggering (an out-of-scope question should call no tool at all).
- **Observability**: every request writes a trace (tools called, final decision, latency) to a DynamoDB table.

## Stack

Python · [Strands Agents](https://github.com/strands-agents/sdk-python) · Amazon Bedrock (Claude Haiku 4.5, Titan Embeddings, Knowledge Base, Guardrails) · AWS Lambda + API Gateway (HTTP API) · DynamoDB · S3 Vectors · HubSpot API · AWS CDK (Python)

**S3 Vectors instead of OpenSearch Serverless** for the Knowledge Base's vector store: OpenSearch Serverless bills a fixed minimum even when idle (~$300-700/month), S3 Vectors (released December 2025) is pay-per-use, with no infrastructure to manage.

## Architecture

Diagram of the real infrastructure by phase (not the initial plan, what actually runs): [see the artifact](https://claude.ai/artifact/JmC1Jk61bKFFhz43yuGBqP).

## Status

All 4 planned phases are built and validated end to end (local + real deployment):

- **Phase 0** — local prototype, 3 stubbed tools, validating the autonomous tool-choice pattern.
- **Phase 1** — Lambda + API Gateway deployment via CDK, real HubSpot connection.
- **Phase 2** — real RAG on Bedrock Knowledge Base (S3 Vectors).
- **Phase 3** — Bedrock Guardrail + observability (`traces` table).

Full detail on decisions and bugs encountered in [`docs/PROJECT.md`](docs/PROJECT.md).

## Running locally

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
# .env at the project root with HUBSPOT_PRIVATE_APP_TOKEN=...
cd src && python3 run_tests.py   # readable demo
python3 evals.py                 # automated eval suite
```

## Deploying

```bash
cd infra
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cdk bootstrap && cdk deploy
# then trigger the Knowledge Base ingestion (CloudFormation doesn't do it):
aws bedrock-agent start-ingestion-job --knowledge-base-id <id> --data-source-id <id>
```

## Known limitations

- IAM permissions are intentionally broad for this personal prototype (several `*FullAccess` policies), to be tightened before any real client use.
- An order discrepancy detected without an explicit customer complaint still triggers an escalation, a behavior not yet settled, documented in `docs/PROJECT.md`.
