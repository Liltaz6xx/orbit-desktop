# ORBIT Desktop 0.7.0 beta 2

This beta adds an installer for Windows 11 x64. Setup installs for your Windows account and downloads a private Python runtime on first install. It creates a Start menu entry and offers a desktop shortcut, checked by default.

Open **Discord** in ORBIT and enable activity sharing to show **Playing ORBIT** on your Discord profile while the app is running. Discord desktop and its activity-sharing setting control visibility.

## Install

Download and run the **Windows x64 Setup EXE**. For local AI, install Ollama and run `ollama pull qwen2.5:1.5b` in PowerShell. To enable Kokoro, use **Download Kokoro voice** in the ORBIT Desktop Start menu folder. The source ZIP remains available.

Run a newer installer to update an installed copy. Setup uses the existing location and preserves the public ORBIT profile. The installer is unsigned. The attached SHA-256 file lets you verify the download against this release.

## Beta notes

- Local data lives in `%LOCALAPPDATA%\ORBIT Desktop`.
- CPU synthesis can pause between chunks. Use **Read reply** if audio is unavailable.
- App availability depends on your Windows installation. ORBIT asks for permission on the first use of each app or folder in a session and on every lock request.
