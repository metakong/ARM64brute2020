# DSIE Edge Node Architecture Reference

This document outlines the system-level architecture, environment routing, and extreme hardware optimizations applied to the DSIE (Dynamic Swarm Intelligence Engine) Edge Node. It serves as the definitive reference for developers interacting with this environment.

## Hardware & Operating System
- **Architecture:** ARM64
- **Processor:** Snapdragon 8cx Gen 2 @ 3.15 GHz (8 Cores)
- **OS:** Windows 11 Home (Custom Debloated/Optimized)

## Storage & Environment Routing (The Dev Drive)
To eliminate OS-level I/O bottlenecks and protect the primary OS drive from read/write degradation during intense OSINT scraping, all heavy operations are routed to a dedicated ReFS Virtual Hard Disk (Dev Drive).
- **Drive Mapping:** The Dev Drive is permanently mounted at `Z:\`.
- **Global Variables:** System and User `%TEMP%` and `%TMP%` are forcibly routed to `Z:\SystemTemp`.
- **Package Caches:** Both Python (`Z:\pip_cache`) and Node (`Z:\npm_cache`) download directly to the Dev Drive.
- **AI Model Cache:** The Foundry Local SDK caches models natively to `Z:\foundry_cache`.

## Security & Performance Optimizations
The system is engineered as a zero-latency, dedicated "Master Commander" node. Consumer-grade background processes and heavy security mitigations have been neutralized to dedicate 100% of hardware cycles to the NPU and Python inference pipelines.

- **VBS & Core Isolation:** Virtualization-Based Security (VBS) is disabled to remove NPU/CPU virtualization overhead.
- **Anti-Malware Hooks:** Windows Defender real-time protection and background scanning are disabled (via registry and WMI) to prevent silent file-locking and latency spikes during massive PocketBase/SQLite transactions.
- **Telemetry & Indexing:** `DiagTrack`, `SysMain` (SuperFetch), and `WSearch` (Windows Search) are permanently disabled.
- **Consumer Bloat Neutralized:** - OEM telemetry (Samsung System/OSD Services)
  - Cloud synchronization (OneDrive polling tasks)
  - Gaming services (Xbox Live Auth, GameSave)
  - Print Spooler and Phone Link
- **Network Attack Surface:** SMB and File/Printer Sharing (`LanmanServer`) are disabled, actively closing vulnerable local network ports (139, 445) since this node does not accept inbound file drops.
- **Auto-Updaters:** Chrome and Edge background scheduled updaters are disabled to prevent sudden API throttling during the 2:00 AM pipeline runs.

## Core Microservices Stack
The local swarm communicates via a decoupled architecture bound strictly to `localhost` (`127.0.0.1`).

- **Port 8000:** FastAPI Mercenary Router (Dynamic routing to 21+ Cloud LLM APIs).
- **Port 8080:** Python HTTP Local Server (Serving the HTML CEO Dashboard).
- **Port 8090:** PocketBase (The "Cognitive Bus" and real-time transcript database).

## Automation & Orchestration
Windows Task Scheduler acts as the central cron engine. Because the global `%TEMP%` relies on a virtual `Z:\` drive, standard startup scripts will crash if executed before the virtual disk is mounted by the kernel.

- **Mount Forge ReFS:** A dedicated task to ensure the VHDX Dev Drive mounts at system boot.
- **DSIE_Master_Boot (Interactive):** Triggers `At Logon` (30s delay). It executes a `C:\` drive wrapper script (`full_boot.bat`) that temporarily redirects the temp variables back to `C:\`, polls for the `Z:\` drive, and then silently launches the Core Microservices Stack.
- **DSIE_Night_Shift (Headless):** Triggers daily at `02:00 AM` (`-WakeToRun` enabled). Wrapped in `C:\night_shift_wrapper.bat` to prevent directory resolution errors, it spawns `agent8_orchestrator.py` to execute the global OSINT scraping pipeline.
