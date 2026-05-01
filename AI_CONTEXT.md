# DSIE Codex - AI Context & Operating Rules
**System Status:** ONLINE | **Hardware Target:** ARM64 / Snapdragon 8cx Gen 2 (8GB RAM)

> **ATTENTION ALL AI AGENTS:** You must read and adhere to these rules before executing any code, writing any scripts, or suggesting architecture changes.

## 1. Immutable Hardware & Security Rules
* **The Dev Drive Constraint:** All heavy operations, global `%TEMP%` variables, package caches, and database files reside on the ReFS Virtual Drive mapped to `Z:\`. Do NOT attempt to execute IO-heavy tasks on the `C:\` drive.
* **The Security Vault (CRIT-1 Resolved):** All sensitive credentials (e.g., `.env`, `client_secret.json`, `token.json`, GCP service keys) are isolated in `Z:\foundry_project\secrets\`. 
    * *Agent Directive:* You are strictly forbidden from reading, modifying, or asking for the contents of the `secrets/` directory. Assume all authentication is correctly formatted and active.
* **The NPU Trojan Horse:** The Microsoft Foundry Local (MSFL) SDK is purposefully configured to load `qwen2.5-0.5b`. This directory houses custom 4B INT4 Kaggle weights. The global config affinity forces this onto the **Qualcomm Hexagon NPU (QNN)**. 
    * *Agent Directive:* Do NOT attempt to "correct" the model string in `dsie_core.py` to point to a different model folder, or you will break the NPU routing.

## 2. Architectural Pillars
* **The OSINT Factory:** Python map-reduce agents (1-8) handling data pipelines.
* **The Interactive Edge:** `dsie_core.py` managing real-time NPU inference.
* **The Cognitive Bus:** PocketBase running on port 8090 acting as the central SQLite router.
* **The Presentation Layer:** SvelteKit/Tailwind dashboard and FastAPI Mercenary Router.

## 3. Rolling Architectural Changelog
* **[2026-05-01] Operation Ironclad:** Centralized all root-level credentials into `secrets/`. Patched `dsie_utils.py`, `gdrive_mcp.py`, and all core agents to route to the new vault. Updated `.gitignore`.
* **[2026-05-01] Hardware Verification:** MSFL diagnostic probe successfully confirmed `QnnExecutionProvider` (Hexagon NPU) is actively handling the local Qwen payload.
