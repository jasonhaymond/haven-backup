# Windows clients -- not supported yet

[← Back to README](../README.md) · [Client enrollment](CLIENT_ENROLLMENT.md) ·
[Architecture](ARCHITECTURE.md) · [Borgmatic integration](BORGMATIC_INTEGRATION.md) ·
[Security](SECURITY.md)

## Contents
- [Why it isn't a checkbox](#why)
- [Options being considered](#options)
- [What's needed to decide](#to-decide)

**Status: nothing on this page is built.** It records why Windows clients aren't part of
[client enrollment](CLIENT_ENROLLMENT.md) yet, and which options are on the table.

<a id="why"></a>
## Why it isn't a checkbox

Haven Backup is built on Borg and borgmatic, and neither runs natively on Windows:

- **Borg** has no official native Windows build. Community Cygwin/MSYS2 builds exist but
  are experimental, and a backup tool isn't the place to rely on one.
- **borgmatic** doesn't support Windows at all.
- **"Backup now"** needs an SSH server on the client. Windows' optional OpenSSH Server works,
  but its forced commands run through `cmd.exe`/PowerShell, not a Linux shell.

<a id="options"></a>
## Options being considered

| Option | How it works | Main drawback |
|---|---|---|
| **WSL2** | Install WSL2 + Ubuntu, run the existing Linux enrollment inside it, reading `C:\` through `/mnt/c`. A Windows scheduled task wakes WSL and runs the backup. | No Volume Shadow Copy (VSS): files that are open or locked (Outlook PSTs, running databases, some app data) are skipped or copied mid-write. Slow on large NTFS trees. |
| **WSL2 + VSS** | As above, but the scheduled task (elevated) first takes a VSS shadow copy, mounts it, and backs up from the snapshot. | Most work to build and test; needs an elevated task and careful cleanup of shadow copies. |
| **Different tool for Windows** | Use a Windows-native backup tool (e.g. restic or Kopia, both with VSS support) for Windows hosts. | The portal only understands Borg today, so Windows backups would need a second integration to appear on the dashboard. |

<a id="to-decide"></a>
## What's needed to decide

- A real Windows machine to test on, since none of this can be verified in the Linux
  containers used to test Linux enrollment.
- Which files actually matter on the Windows hosts. If they include files that are always
  open, plain WSL2 isn't good enough and it's WSL2 + VSS or a different tool.
