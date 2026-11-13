# ORBIT Desktop 0.7.0 beta 1

ORBIT is a Windows 11 assistant you type to and hear in a British voice. This is the first public beta, with the animated orb, local AI, saved facts and confirmation for Windows actions.

## Install

Download the Windows ZIP and extract it. Install Python 3.12 and Ollama, run **Setup_ORBIT.bat**, and pull the default model with `ollama pull qwen2.5:1.5b`. Launch with **Run_ORBIT.bat**. The ZIP includes setup instructions and a system checker. Voice assets are optional and can be downloaded during setup.

## Beta notes

- Local data lives in `%LOCALAPPDATA%\ORBIT Desktop`.
- CPU synthesis can pause between chunks. Use **Read reply** if audio is unavailable.
- App availability depends on your Windows installation. ORBIT asks for permission on the first use of each app or folder in a session and on every lock request.
