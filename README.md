> **Transparency Notice:** This documentation was authored by Claude Sonnet 4.6 (Anthropic) under direct human oversight — the same iterative, human-in-the-loop AI partnership methodology used to architect and build every system in this portfolio.

> **Portfolio Context** | **Sean Deardorff** — Strategic Operations & Business Development
>
> This repository is an artifact of high-velocity, AI-partnered process engineering. It demonstrates how the author builds resilient, automated business machinery — translating the same decoupled logic, governance, and defensive optimization used to manage open sales territories and corporate operations into working code.
>
> **Career Connection:** This bare-metal hardware optimization project reflects the same system-level resourcefulness Sean demonstrated at eBay Enterprises — operating with privileged access to AS/400 terminals (IBM 5250), executing nightly EDI/SQL batch processing, and uncovering hidden metric manipulation through deep formula tracing. When the abstraction layer fails or the vendor says "unsupported," the instinct is the same: go deeper into the machine and make it work.
>
> [View Full Portfolio →](https://github.com/metakong/sean-deardorff)

---

# 🦍 ARM64brute2020: The NPU Liberation Project

![Architecture](https://img.shields.io/badge/Architecture-ARM64-blue) ![OS](https://img.shields.io/badge/OS-Windows_11_on_ARM-blueviolet) ![Device](https://img.shields.io/badge/Device-Galaxy_Book_Go_5G-lightgrey) ![Status](https://img.shields.io/badge/Status-Foundational_Alpha-success)

AI-Assisted project.  Special thanks to Gemini & Claude.  Below is my AI-generated README.md written in the most professional Linus Torvalds tone that Gemini could imagine!
---

## 🛑 The Philosophy (Why This Exists)

Cloud dependencies are a crutch, and OS-level abstraction layers are usually just excuses to hide poor hardware utilization. 

This repository was born from a fundamental disagreement with modern software provisioning. The Microsoft Foundry Local SDK is a brilliant piece of engineering, but it relies on Windows Machine Learning (WinML) and background Windows Update telemetry to "authorize" your hardware to use the NPU. If you debloat your OS to gain performance, the SDK assumes you are on a generic CPU, blacklists your machine from the Azure hardware catalog, and leaves your dedicated Hexagon tensor cores gathering dust.

Software shouldn't dictate what hardware you're allowed to use. 

This project is a complete, autonomous, offline-first AI ecosystem. It demonstrates how to reverse-engineer closed-source cloud telemetry, force ONNX runtime execution onto bare-metal DSPs, bypass hardcoded OS memory limits, and build a highly modular multi-agent system on older ARM64 silicon.

---

## 🏗️ System Architecture

This isn't just a voice assistant; it is a full-stack, decoupled intelligence node split into distinct functional pillars to maximize the 8GB RAM constraint.

### 1. The OSINT Factory (The Night Shift)
* **Stack:** Python, Requests, BeautifulSoup.
* **Function:** A classic Map-Reduce autonomous pipeline (`agent1` through `agent8`). These agents wake up overnight, scrape global intelligence, score it, extract the signal from the noise, and write daily consolidated briefings. Because they run offline, they don't compete with real-time NPU resources.

### 2. The Cognitive Bus (The Memory Layer)
* **Stack:** PocketBase (SQLite).
* **Function:** Because nobody needs a Kubernetes cluster to store daily news. PocketBase acts as a lightning-fast, local REST API that bridges the overnight Python agents, the real-time Voice Assistant, and the Svelte frontend. It handles state, transcripts, and the "Vault" memory system without file-locking collisions.

### 3. The Interactive Edge (Codex Voice Stack)
* **Stack:** Microsoft Foundry Local, ONNX Runtime, Qualcomm AI Engine Direct (QAIRT).
* **Function:** The real-time interface. It runs **OpenAI Whisper (Tiny)** and **Qwen 2.5 (4B int4)** directly on the Hexagon NPU. It listens, reads the OSINT briefs from PocketBase, and responds verbally with near-zero latency.

### 4. The Presentation Layer (WIP)
* **Stack:** SvelteKit, Tailwind CSS.
* **Function:** A reactive, local HTML dashboard that visualizes the data inside PocketBase. 

---

## 🛠️ The Hack: Forcing the Hexagon NPU (A Developer's Guide)

If you are running an older Snapdragon compute platform (7c, 8cx Gen 2) and Foundry Local is forcing you onto the `CPUExecutionProvider`, here is exactly how to break the locks.

### Step 1: Gutting VBS & Debloating
First, disable Virtualization-Based Security (Core Isolation). Running local AI through a hypervisor translation layer destroys latency. We want bare-metal memory-mapped I/O.
* See `tools/optimize_system.ps1` for the exact Registry and Environment Variable routing needed to keep your C: drive pristine by mapping Python and NPM caches to a dedicated Z: drive.

### Step 2: The QAIRT DLL Injection
Because we gutted WinML telemetry, the OS won't download the Qualcomm Execution Provider. You must manually download the Qualcomm AI Runtime (QAIRT) and hard-link it into the Python environment *before* the SDK initializes:
```python
qairt_bin = r"Z:\QCDrivers\qairt\2.45.0.260326\bin\arm64x-windows-msvc"
os.add_dll_directory(qairt_bin)
os.environ["PATH"] = qairt_bin + os.pathsep + os.environ["PATH"]
```

### Step 3: Bypassing the Azure Catalog & The Memory Trojan
Foundry Local limits model allocation to ~60% of total system RAM to prevent OS crashes (giving us a hard ceiling of 4.8GB). Furthermore, Azure will block your machine from downloading `-qnn-npu` variants if it doesn't detect WinML.
**The Fix:**
1. Use `Configuration(additional_settings={"ExecutionProvider": "QnnExecutionProvider", "EpDetectorOverride": "true"})` to globally force the C# backend to use the NPU.
2. Request a generic, smaller model (e.g., `qwen2.5-1.5b-instruct-qnn-npu:2`) from the catalog so it generates the correct Hexagon DSP folder structure.
3. Shut down the script, go into `Z:\foundry_cache\models\Microsoft\...` and mercilessly overwrite the 1.5B weights with your custom 4B int4 `.onnx` weights. The system will load the 4B model into the NPU footprint without triggering the RAM gatekeeper.

### Step 4: The Dev Drive Mount Race & Task Scheduler Ignition
If you are using a Windows "Dev Drive" (VHDX/ReFS) to store your environment, standard Startup Folders and VBScripts will fail silently. The OS will attempt to spawn the command shell before the Virtual Disk Service mounts the drive. Because our global %TEMP% variable points to the Dev Drive, the shell crashes instantly upon launch.

The Fix: 
1. Abandon the shell:startup folder.
2. Create a "Bootstrapper" batch file on your primary C: drive that forces a local temp environment, polls for the Dev Drive to mount, and then hands execution to the NPU:

```batch
@echo off
:: Force local temp to C: to prevent CMD crash if Z: is unmounted
set TEMP=C:\Windows\Temp
set TMP=C:\Windows\Temp
:POLL
if not exist "Z:\foundry_project\core\dsie_core.py" (
    timeout /t 2 /nobreak > nul
    goto POLL
)
cd /d "Z:\foundry_project"
start "" "Z:\foundry_project\venv\Scripts\python.exe" "core\dsie_core.py"
```

Use the Windows Task Scheduler to trigger this script At log on with a 30-second delay, ensuring it runs with "Run only when user is logged on" to utilize the Interactive Admin Token (bypassing SeBatchLogonRight restrictions and allowing hardware mapping).


### Step 5: The Whisper Squelch (Anti-Hallucination)
OpenAI's Whisper model hallucinates aggressively when fed pure room static (often outputting *"Thank you for watching"*). To fix this, `dsie_core.py` implements a hard mathematical VAD (Voice Activity Detection) threshold (`rms > 0.05`), a 1-second minimum audio gate, and a regex blacklist to instantly drop known static hallucinations before they ever wake up the LLM.

---

## 🤝 Conclusion

This repository is an ongoing exploration of edge computing, model optimization, and autonomous agent orchestration. It proves that with enough patience, a solid understanding of memory mapping, and a willingness to break a few abstraction layers, you can squeeze modern AI performance out of "outdated" silicon. 

**Here's to building systems that work, no matter what the documentation says is "impossible."**

## Security Update (2026-05-01)

This repository has undergone a security hardening phase (Operation Ironclad). Key updates include:
- **Credential Vaulting**: Sensitive environment variables and API keys have been moved to a localized secrets/ directory.
- **Path Remediation**: All agents and core utilities have been updated to target the secure vault location.
- **Infrastructure Hardening**: Git ignore policies have been enforced to prevent accidental exposure of local configuration files.
- **NPU Optimization**: Validated local hardware execution paths for Qualcomm Hexagon NPU acceleration.

---
### Architect's Log: The Edge Node Evolves
**Date:** May 2026
**Update: Bare-Metal Communications Hub & IMAP/SMTP Integration**

We just deployed the **Communications Hub**, a zero-dependency Gmail MCP server that operates directly on bare-metal IMAP and SMTP protocols over SSL. We've officially bypassed the bloated `google-api-python-client` SDK and its associated OAuth overhead. Why use a multi-megabyte library to read a text message? 


---
### Architect's Log: The Chromium Purge (Operation Bare-Metal)
**Date:** May 2026
**Update: Tauri v2 Dashboard Migration (YOLO-1)**

If you enjoy paying a 600MB "RAM tax" just to render a basic HTML table in a bloated Chromium shell, then this update isn't for you. For the rest of us who value hardware efficiency, the CEO Dashboard has been migrated to a native **Tauri v2** shell. 

We've officially ditched the web browser. The dashboard now runs as a lean, bare-metal Windows executable leveraging the native WebView2 engine. The result? A memory footprint drop from ~600MB to under 40MB. We've also aligned the CORS policies across the Mercenary Router and PocketBase to authorize the `tauri://localhost` origin, ensuring the "CEO Omni-Pane" has secure, low-latency access to the local intelligence bus.

Because let's be honest: if your dashboard requires more RAM than the AI models it's monitoring, you're doing it wrong. The silicon belongs to the agents, not the browser engine.

---
### Architect's Log: Final Linker Execution (The Native Absolute)
**Date:** May 2026
**Update: Tauri Compilation Finalized (SOP-04)**

The linker has finished its job, and for once, it didn't complain about missing MSVC ARM64 build tools because I actually provisioned them correctly. The CEO Dashboard is now a fully compiled, native Windows ARM64 executable (`dsie_codex.exe`). 

We've finalized the 40MB standalone WebView2 Omni-Pane. No more JIT-compiling JavaScript in a bloated browser instance just to look at a data feed. The binary is small, the startup is instant, and the memory footprint is exactly what it should be: negligible. If you're still running this through a web browser, you're just wasting silicon. Push confirmed. 

---
### Architect's Log: Gutting the Race Conditions & Regex Guillotines
**Date:** May 2026
**Update: MCP Nexus Daemon Hardening & Structured Output Enforcement**

I refuse to accept silent failures caused by lazy threading. The MCP Nexus was arbitrarily sleeping for 100ms hoping the async loop would start, leaving the ARM CPU to essentially roll the dice. We've ripped out the `time.sleep()` bloat and replaced it with a deterministic `threading.Event()` lock. The main thread now properly halts until the daemon sets the flag. It's clean, it's absolute, and it prevents frozen coroutines when the silicon is under heavy load.

Furthermore, we've executed the Regex Guillotine. The `clean_json_response` function in `dsie_utils.py` was wasting NPU cycles slicing up markdown tags like a junior script kiddie. This is 2026. The Mercenary Router now natively enforces strict API-level JSON schemas (`response_format`). We pass the formatting burden straight back to the cloud providers where it belongs, ensuring pure data hits the DSIE core without the overhead of fragile string manipulation.
