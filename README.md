# ARM64brute2020: The DSIE Codex & MAF4A Engine 🦍💻

![Architecture](https://img.shields.io/badge/Architecture-ARM64-blue) ![OS](https://img.shields.io/badge/OS-Windows_11_on_ARM-blueviolet) ![Device](https://img.shields.io/badge/Device-Galaxy_Book_Go_5G-lightgrey) ![Status](https://img.shields.io/badge/Status-Foundational_Alpha-success)

## 📌 Project Overview

**Timeline:** April 21, 2026 – April 27, 2026  
**Effort:** ~100 Hours (Including one clinically unadvisable all-nighter)

**ARM64brute2020** is an AI-assisted project born out of sheer necessity, budget constraints, and a complete inability to know when to quit. 

It began as a silicon-level trench war: forcing modern, localized AI (Microsoft AI Foundry Local) to run natively on an abandoned 2020 ARM64 laptop (Samsung Galaxy Book Go 5G). But once the hardware barrier was broken, the project mutated. It evolved from a localized LLM testbench into the **DSIE Codex**—the foundational architecture for **MAF4A** (Multi-Agent Framework for Automation).

This isn't a polished corporate tutorial. It is a survival guide for ARM64 developers and a blueprint for a distributed, hardware-agnostic "CEO Dashboard" designed to replace traditional browser workflows with autonomous, event-driven intelligence.

---

## 🧱 Phase 1: Breaking the ARM64 Barrier 🤬

If you are attempting to run local AI on a 1st or 2nd generation Windows-on-ARM device (Snapdragon 8cx Gen 2), you already know the pain. You are abandoned by package managers, NPU drivers, and pre-compiled binaries. 

### The Emulation Trap & Compilation Hell 🔥
To build this, we had to bypass the Windows-on-ARM emulation traps and `winget` failures. If you've ever stared at a terminal vomiting `error: subprocess-exited-with-error` while trying to compile Rust toolchains (`aarch64-pc-windows-msvc`) or missing C++ 14.0 build tools just to get a simple Python wheel to install... you understand the nightmare. 

**The Workarounds (How to Replicate):**
1.  **The NPU Driver Hunt 🕵️‍♂️:** Windows 11 doesn't ship with the Snapdragon 8cx Gen 2 Hexagon NPU driver. We had to manually source and inject the `Qualcomm_Hexagon_NPU_Driver-v1.0.0.14` to get `onnxruntime` to acknowledge the silicon.
2.  **Gutting Microsoft AI Foundry:** The official SDK assumes x64 architecture. We unpacked the nested dependencies (`sherpa-onnx`, `espeak-ng-data`), manually sourced the ARM64 static libraries, and surgically injected them. *(Note: The massive 800MB `.lib` binaries have been stripped from this GitHub repo to meet size limits, but the `dependencies/` folder structure shows exactly where you must place them).*
3.  **Model Squeezing:** Standard `.gguf` files will instantly cap this laptop's 8GB shared memory. We utilized Kaggle GPUs to convert models (like Qwen) to `.onnx` and heavily quantize them (`int4`) for edge viability.
4.  **Universal PATH Injection:** Emulated PowerShell instances will frequently drop your CLI bindings. We bypassed scripts entirely, mapping un-emulated `\cmd` folders directly into the deepest OS-level Environment Variables.

**The Win:** A natively executing Qwen model running entirely on-device on a 2020 budget ARM laptop, proving legacy Snapdragon silicon is still viable for edge AI.

---

## 🧠 Phase 2: The MAF4A Evolution (Beyond Chatbots) 🚀

During the 100-hour sprint, deep architectural research revealed a fatal flaw in current AI: existing frameworks (like crewAI) are just bloated "Role-Play Abstractions" that waste tokens on system prompts, while others (LangGraph) are rigid state machines. 

We abandoned them both to build **MAF4A** (Multi-Agent Framework for Automation) based on **Cognitive Event Streaming**.

### The Architecture: "The Iron Spine" 🏗️

Instead of a human doom-scrolling feeds or manually scraping data, this pipeline operates as a distributed system, pushing data sequentially straight into a local PocketBase backend and out to an HTML UI.

* **Sub-Cognitive Offloading:** "Low-IQ" tasks (formatting, data scraping) are offloaded to the local Snapdragon NPU. Only heavy, strategic reasoning is routed to cloud APIs (Groq/Gemini), drastically cutting latency and costs.
* **MCP-Native Connectivity (The "USB" Ports):** Agents do not hard-code API integrations. Using the **Model Context Protocol (MCP)**, the system dynamically discovers your local files, Google Drive, and databases securely.
* **The Sequential Agent Chain:**
    * `agent1_fetcher.py`: Ingests raw XML/RSS data from targeted seed lists.
    * `agent2_scorer.py`: The local NPU evaluates articles against strict "Pillars of Intelligence." Noise is instantly culled.
    * `agent3_extractor.py`: Deep entity and metric extraction on surviving data.
    * `agent4_consolidator.py`: Synthesizes raw facts into executive-level briefs.
    * `agent5_content_creator.py`: Enforces strict JSON schemas for the dashboard.
    * `agent6_dashboard_injector.py`: Pushes structured data to the local PocketBase SQLite DB.
* **Agent 7 (The Evolutionary Historian) 🧬:** The system remembers. It logs today's winning URLs to prevent duplicates and dynamically hunts for *new* target feeds based on today's highest-scoring intelligence, automatically evolving its own intake for tomorrow.

---

## 📂 Repository Structure

```text
ARM64brute2020/
├── core/
│   ├── agent1_fetcher.py
│   ├── agent2_scorer.py
│   ├── ... (Agents 3-7 & Orchestrator)
│   ├── dsie_core.py                 # Core utility and LLM routing
│   └── mcp_nexus.py / gdrive_mcp.py # Model Context Protocol implementations
├── dashboard/
│   └── index.html                   # The clean, vanilla HTML/JS CEO Dashboard
├── bus/
│   └── pocketbase/                  # Local Go/SQLite database and migrations
├── dependencies/                    # The reconstructed Microsoft Foundry SDK tree
│   └── Foundry-Local-main/
└── dsie_boot.vbs                    # Silent execution wrapper
```

---

## 💡 A Note on Competency & AI Assistance

Let's be unequivocally clear: this codebase was heavily AI-assisted. 

If this repository demonstrates any primary competency, it is **simply not being smart enough to know when to give up.** It is the result of arguing with an AI coding assistant for 100 hours, refusing to accept that "hardware limitations," "C++ compilation failures," or "emulation barriers" were valid reasons to abandon the build. 

It is a testament to what a budget-conscious developer can achieve when they combine modern LLM tooling with absolute, relentless, sleep-deprived stubbornness. 

Welcome to the DSIE Codex. Enjoy the code. 🍻