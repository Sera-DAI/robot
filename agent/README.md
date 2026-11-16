# PC agent

A small program that keeps running on Windows, reads the `robot-comandos` queue and shuts the PC down
when the `shutdown` command arrives. It only makes outbound connections (HTTPS to SQS): no port is opened.

It uses only the Python standard library (3.11 or newer, installed from python.org). There is no `pip install`.

## Security rules

- Fixed list of actions (today only `shutdown`). Text from the queue never becomes a command line: the
  message must be exactly `{"versao": 1, "acao": "shutdown"}`; anything else is deleted and ignored.
- A command sent before the agent started, or more than 60 s ago, is discarded. This way a "turn off"
  said while the PC was off does not bring the PC down right after it is turned on.
- The message is deleted from the queue before acting. If it cannot be deleted, nothing is executed.
- The shutdown warns on screen and waits 30 s. To cancel: `shutdown /a`. After the delay, Windows
  closes open programs without asking.
- The access key lives in the Windows Credential Manager. The log never records the key, the secret
  or response bodies.

## Installation (once, after the phase 4 `sam deploy`)

1. Create the access key of the `robot-agente` user (see `infra/README.md`) and keep the ID and secret
   at hand. They appear only once.
2. Open PowerShell as administrator, go into the repository's `agent` folder (an administrator
   PowerShell opens in another folder) and run the installer:

   ```
   cd PATH_TO_THE_REPOSITORY\agent
   powershell -ExecutionPolicy Bypass -File .\install_dedicated_account.ps1
   ```

   It does the following, in this order:

   - creates the local account `robot-agente-svc`, unprivileged and hidden from the login screen,
     with a random password that only Task Scheduler keeps (it is never shown or written to a file);
   - copies the agent to `%ProgramData%\robot-agente\app`, a folder only administrators can change;
   - registers the `RobotAgente` task at Windows startup under that account, so the PC can be shut
     down while it sits at the login screen;
   - opens another window, running as the dedicated account, where you enter the queue URL, the key
     ID and the secret. The secret is typed without being shown and goes straight into that account's
     Credential Manager, not into a file.

   Python must be installed "for all users" (for example under `Program Files`), because the dedicated
   account cannot read your profile. The task runs without administrator privileges.
3. Check `%SystemDrive%\Users\robot-agente-svc\AppData\Local\robot-agente\agent.log`: it should show
   "agent started" and no error. If Windows refuses the shutdown (access denied), grant the account
   the "Shut down the system" right in `secpol.msc`, under Local Policies, User Rights Assignment.
4. Delete the old credential from your own account, if it exists: `cmdkey /delete:robot-agente`.

After updating the repository code, run the installer again to recopy the agent.

### Alternatives

- `install_task.ps1` registers the task under your own account. Its `-Trigger Logon` trigger works
  without a password, but the agent then runs only after you sign in (no shutdown at the login screen).
- To test in the foreground without scheduling (Ctrl+C stops it): `python -m robot_agent.configure`
  and then `python -m robot_agent`, with your own account.

## Removing

```
powershell -ExecutionPolicy Bypass -File .\install_dedicated_account.ps1 -Remove
```

This deletes the task, the dedicated account and the agent copy. If you used `install_task.ps1`:
`Unregister-ScheduledTask -TaskName RobotAgente -Confirm:$false` and `cmdkey /delete:robot-agente`.

## Tests

`python scripts/verify.py --full`, at the repository root. The tests replace the network and
`shutdown`: no test shuts any machine down.

## Known limitations

- The Credential Manager, the scheduled task and the real shutdown only run on Windows: they are manual acceptance.
- The dedicated account, shutdown at the login screen and the setup window running as another account only work on Windows: manual acceptance.
- If the PC clock is off by more than a few minutes, AWS refuses the signature and the log shows HTTP 403.
- The command age compares AWS time with the PC clock. With the clock a few seconds fast, a command
  given in the first seconds after the agent starts is discarded (it appears in the log).
- The task runs the copy in `%ProgramData%\robot-agente\app`, which only administrators can change. Whoever is an administrator of the PC can change what the task runs.
