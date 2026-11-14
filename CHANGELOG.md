# ORBIT changelog

## 0.7.0-beta.2

- Add a per-user Windows 11 x64 Setup EXE with a private Python runtime and verified dependencies.
- Upgrade installed copies in place and keep memories, settings and voice downloads in the user profile.
- Create a Start menu entry and offer a desktop shortcut selected by default on first install.
- Add opt-in Discord activity sharing through the local desktop app.

## 0.7.0-beta.1

- First public Windows beta of ORBIT Desktop.
- Store settings, logs and memory in a dedicated Windows user profile.
- Use local Qwen2.5 1.5B by default and keep model selection configurable.
- Credit Liltaz6xx as ORBIT's creator and use Maker for the current operator.
- Add Windows CI, issue forms and a reproducible release ZIP with a SHA-256 checksum.

## 0.7.0

- Fixed the missing theme imports that prevented startup.
- Redesigned the native Windows window and retained the original orb artwork and Maker Protocol.
- Added four orb states, a compact composer, Stop and an on-demand view of the latest reply.
- Added configurable local Ollama streaming with model checks, cancellable reads and turn IDs.
- Preloaded Kokoro, pipelined synthesis and playback, and added cancellable Windows speech fallback.
- Added versioned SQLite migrations, ranked memory search, explicit deletion prompts and archive invalidation.
- Restricted Windows control to complete typed commands with per-target session permissions and fresh lock confirmation.
- Updated setup and launch scripts, added read-only diagnostics and rotating performance logs, and expanded automated coverage.

## 0.6.0 — Modular Long-Term Memory edition

- Split the existing single-file application into nine focused Python modules plus an entry point.
- Persistent SQLite conversation history and explicitly saved facts.
- Commands to remember, recall, list and forget memories.
- Clear conversation and delete-all commands; explicit confirmation for wiping saved data.
- Kept Maker identity in the system prompt.
- Kept Ollama Qwen2.5 3B, streaming response chunks and Kokoro British masculine voice.
- Kept animated audio-reactive sphere using the original PNG assets.
- Kept allowlisted Windows apps/folders, system info and consent dialogs.
- Added one-click Windows setup, model downloads, launcher and environment checker.
- Added automated memory and action routing tests.
- Hardened hypothetical/negated Windows action request checks.

## Earlier foundations

- 0.5 — Windows application launching, folder navigation, system status and permission checks.
- 0.4 — Kokoro neural voice, speech-reactive core, fast streaming speech and Maker Protocol.
- 0.3 — Local Ollama language model and per-session conversation context.
- 0.2 — Original transparent orb visuals.
