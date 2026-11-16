# Infrastructure (AWS SAM)

Region `us-east-1`, the one the Alexa documentation listed for Portuguese (Brazil) on 2026-11-10
(check the current documentation before deploying).
The template creates the Lambda `robot-lambda`, the table `robot-tokens`, the queue `robot-comandos`
and the IAM user `robot-agente` (it can only read and delete messages from that queue).

For a full walkthrough from zero, including the Alexa console and the Windows agent, see
[`docs/installation-guide.md`](../docs/installation-guide.md).

## Before the deploy

1. Phases 1 and 2 of the plan are done.
2. Create the Smart Home skill in development mode in the Alexa Developer Console, with the language
   Portuguese (Brazil), and note the skill ID.
3. Under Permissions, turn on "Send Alexa Events" and note the Alexa Client Id and Alexa Client Secret.

## Manual deploy

```
sam build --template infra/template.yaml
sam deploy --guided --template infra/template.yaml --region us-east-1 --profile robot --capabilities CAPABILITY_NAMED_IAM
```

`--guided` asks for the four parameters (`SkillId`, `PcMac`, `LwaClientId`, `LwaClientSecret`).
The MAC must use the format `XX-XX-XX-XX-XX-XX`, with hyphens.
They live only in AWS. `samconfig.toml` is in `.gitignore` and must never be committed.

After the deploy, copy the function ARN into the skill's "Default endpoint" field.

`--capabilities CAPABILITY_NAMED_IAM` is required from phase 4 on, because the template creates an
IAM user with a fixed name. Without it the deploy fails.

## Phase 4: queue, agent and turning off

1. Deploy again (commands above). The `QueueUrl` output shows the queue URL; it contains the account
   number and does not go into Git.
2. Create the agent's access key. The secret appears only once, only in the terminal:

   ```
   aws iam create-access-key --user-name robot-agente --profile robot
   ```

3. Install the agent on the PC following `agent/README.md`. The secret is typed into the agent's
   configuration and goes to the Credential Manager; do not save it in a file. Close the terminal
   afterwards.

### Phase 4 acceptance (manual, on the platform)

Save whatever is open first: these tests really shut the PC down.

1. With the agent running, open the `robot-comandos` queue in the SQS console, "Send and receive
   messages", and send a message outside the list, for example `{"versao": 1, "acao": "reboot"}`.
   Nothing should happen, and the agent log should record the discard.
2. Send `{"versao": 1, "acao": "shutdown"}`. Windows should warn and shut down in 30 s
   (`shutdown /a` cancels).
3. Turn the PC on and, without signing in (login screen), say "Alexa, desligar o PC". It should shut down.
4. With the PC off, say "Alexa, desligar o PC" and then turn the PC on. It should stay on.
5. "Alexa, ligar o PC" should keep working.

If the agent was registered with `-Trigger Logon`, do step 3 after signing in and note that in the result.

To rotate the agent's key, always use the user name so you do not touch another key:

```
aws iam list-access-keys --user-name robot-agente --profile robot
aws iam delete-access-key --user-name robot-agente --access-key-id OLD_KEY_ID --profile robot
aws iam create-access-key --user-name robot-agente --profile robot
```

Then run `python -m robot_agent.configure` again.

## Known limitations

- The automated tests do not exercise Alexa, Wake-on-LAN or the deployed Lambda.
- The internal invocation (`robot_interno`) is not signed: anyone with `lambda:InvokeFunction` in the
  account can trigger a legitimate "turn on". Accepted because this is a personal skill; reassess if
  the skill is published.
- The parameters become Lambda environment variables and are visible to anyone with access to the
  account's console.
- Power state is not queried: Alexa does not know whether the PC is on, and answers "ok" to turning
  off even if the agent is stopped.
- The `robot-agente` key is long-lived. It can only read and delete messages from the queue: whoever
  gets it can at most prevent a shutdown, never cause one.
- Anyone with `sqs:SendMessage` in the account can shut the PC down. Accepted because this is a
  personal account.
