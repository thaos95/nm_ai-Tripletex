# NM i AI 2026 — Competition Documentation

Documentation fetched from the official MCP docs server (`https://mcp-docs.ainm.no/mcp`).

## Challenges

### NorgesGruppen Data (Object Detection) — **Active task for this repo**

- [Overview](norgesgruppen-data/overview.md) — Task overview, training data, annotation format
- [Submission](norgesgruppen-data/submission.md) — Zip structure, run.py contract, sandbox environment, security restrictions
- [Scoring](norgesgruppen-data/scoring.md) — Hybrid mAP scoring (70% detection + 30% classification)
- [Examples](norgesgruppen-data/examples.md) — Random baseline, YOLOv8 example, ONNX inference, common errors

### Grocery Bot (Pre-competition warm-up)

- [Overview](grocery-bot/overview.md) — Challenge overview, difficulty levels, quick start
- [Mechanics](grocery-bot/mechanics.md) — Store layout, bot rules, order system, actions
- [Endpoint](grocery-bot/endpoint.md) — WebSocket protocol, game state format, bot response format
- [Scoring](grocery-bot/scoring.md) — Score formula, leaderboard, daily rotation
- [Examples](grocery-bot/examples.md) — Example Python bot, deployment, debugging tips

### Tripletex (AI Accounting Agent)

- [Overview](tripletex/overview.md) — Task overview, how it works, task categories
- [Endpoint](tripletex/endpoint.md) — /solve endpoint spec, Tripletex API reference
- [Scoring](tripletex/scoring.md) — Field-by-field verification, tier multipliers, efficiency bonus
- [Examples](tripletex/examples.md) — Code examples, API usage, common errors, optimization tips
- [Sandbox](tripletex/sandbox.md) — Free sandbox account for API exploration

### Astar Island (Norse World Prediction)

- [Overview](astar-island/overview.md) — Task overview, concept, key constraints
- [Mechanics](astar-island/mechanics.md) — Simulation lifecycle, terrain types, settlement dynamics
- [Endpoint](astar-island/endpoint.md) — REST API specification, all endpoints
- [Scoring](astar-island/scoring.md) — Entropy-weighted KL divergence scoring
- [Quickstart](astar-island/quickstart.md) — Authentication, API examples, submission code

## MCP Server

```bash
claude mcp add --transport http nmiai https://mcp-docs.ainm.no/mcp
```
