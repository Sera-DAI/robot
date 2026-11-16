# Installation guide

This guide takes you from nothing to "Alexa, turn on the PC" and "Alexa, turn off the PC" working on
your own hardware and your own accounts. Nothing here is shared with anyone else: you deploy your own
AWS stack, create your own Alexa skill, and run the agent on your own PC.

Plan for about two hours the first time. Most of it is waiting on account setup and on the Alexa console.

## How it works (one paragraph)

A private Alexa Smart Home skill (development mode, visible only to your Amazon account) calls an AWS
Lambda. **Turn on** makes the Echo broadcast a Wake-on-LAN packet. **Turn off** puts a `shutdown`
action on an SQS queue, and a small Python agent running on the PC reads the queue and shuts Windows
down. The PC only makes outbound connections; no port is opened to the internet. See `README.md`.

## 1. What you need

| Item | Notes |
| --- | --- |
| A desktop PC on **Ethernet** | Wake-on-LAN from a full shutdown is only reliable over a cable (decision D2). |
| An Echo device on the same network | Tested on an Echo Dot (5th generation) with the language set to Portuguese (Brazil). |
| An Amazon account | The **same** account must own the Echo and the Amazon Developer account. A skill in development mode is only visible to its owner. |
| An AWS account | The target cost is zero. See "Costs" below. |
| Windows 10 or 11 on the PC | The agent is Windows only. |
| Python 3.11 or newer on the PC | From python.org. The agent uses only the standard library, so there is no `pip install`. |
| AWS CLI v2 and AWS SAM CLI | On the machine you deploy from (can be the same PC). |
| Git | To clone this repository. |

## 2. Prepare the PC for Wake-on-LAN

Do this first and test it before touching AWS. If this does not work, nothing else will.

1. Enable Wake-on-LAN in the BIOS/UEFI (names vary: "Wake on LAN", "Power on by PCI-E").
2. In Windows, open Device Manager, your network adapter, Properties.
   - Advanced tab: enable "Wake on Magic Packet" (and disable energy-saving Ethernet options).
   - Power Management tab: allow the device to wake the computer, and allow only a magic packet to do so.
3. In Windows power settings, turn **Fast startup** off. It can prevent wake from a full shutdown.
4. Find the adapter's MAC address (`ipconfig /all`, "Physical Address"). It looks like `00-14-22-01-23-45` (this one is a made-up example).
5. Test it: shut the PC down completely and wake it with any Wake-on-LAN app on a phone on the same
   Wi-Fi/network, using that MAC. In the original build the first failure was a mistyped MAC in the
   test app, so check the address if nothing happens.

Keep the MAC private. It is passed to the deploy as a parameter and never committed.

## 3. Create the AWS account and CLI profile

1. Create an AWS account and pick **`us-east-1`** as the region. This region was the one the Alexa
   documentation listed for Portuguese (Brazil) when this project was built; check the current Alexa
   documentation for your language before deploying.
2. Protect the root user with MFA and create an administrator IAM user (also with MFA) for daily use.
3. Set a budget alert (for example US$ 1) so a mistake never turns into a surprise bill.
4. Sign in with the CLI and keep the work in a named profile (the examples use `robot`):

   ```
   aws login --profile robot
   aws sts get-caller-identity --profile robot
   ```

Tip: AWS accounts created with the newer sign-up flow may pin the region for you. If your account is
pinned to a region other than the one you need, create the account again with the advanced sign-up.
Confirm the region with `aws lambda list-functions --region us-east-1 --profile robot`.

## 4. Create the Alexa skill

In the [Alexa Developer Console](https://developer.amazon.com/alexa/console/ask), signed in with the
Amazon account that owns your Echo:

1. Create skill. Name it anything. Choose the **Smart Home** model. Select your locale (for example
   Portuguese (BR)) and use payload version 3. Hosting: provision your own.
2. Copy the **Skill ID** (`amzn1.ask.skill.<uuid>`). You need it for the deploy.
3. Permissions tab: turn on **Send Alexa Events** and copy the **Alexa Client Id** and **Alexa Client
   Secret**. These are *not* the same as the Login with Amazon security profile used for account
   linking. Mixing the two makes the authorization-code exchange fail.
4. Leave the "Default endpoint" empty for now. You fill it after the deploy (step 5).

Account linking is configured in step 6, because it needs your skill's redirect URLs.

## 5. Deploy the AWS stack

From the repository root, on the machine that has your AWS profile:

```
sam build --template infra/template.yaml
sam deploy --guided --template infra/template.yaml --region us-east-1 --profile robot --capabilities CAPABILITY_NAMED_IAM
```

- It asks for four parameters: `SkillId`, `PcMac` (the MAC from step 2, with hyphens, `XX-XX-XX-XX-XX-XX`),
  `LwaClientId` and `LwaClientSecret` (from step 4.3).
- When it asks **"Save arguments to configuration file"**, answer **N**. Answering Y writes your
  secrets into a local file. `samconfig.toml` is in `.gitignore`, but do not rely on that.
- `CAPABILITY_NAMED_IAM` is required because the template creates an IAM user with a fixed name.

When it finishes, copy the **Lambda function ARN** (function `robot-lambda`) into the skill's
**Default endpoint** in the Alexa console and save. The template already grants the Alexa Smart Home
service permission to invoke the function, and only for your Skill ID. If the console rejects the ARN,
see "Troubleshooting".

Note the `QueueUrl` stack output. It contains your account number and must not go into Git.

## 6. Link the skill to your account

The skill needs account linking so Alexa can send events back (Wake-on-LAN needs this). It uses Login
with Amazon (LWA). This has two parts, and **two different pairs of client id and secret** are
involved. Do not mix them up:

| Pair | Where it comes from | Where it goes |
| --- | --- | --- |
| Alexa Client Id / Secret | Skill, Permissions tab (step 4.3) | The `sam deploy` parameters only |
| Security profile Client ID / Secret | Login with Amazon console (below) | The skill's Account Linking page only |

1. Open the [Login with Amazon console](https://developer.amazon.com/loginwithamazon/console/site/lwa/overview.html)
   and choose **Create a New Security Profile**. Give it a name and a short description. The
   **Consent Privacy Notice URL** field requires a link; any valid `https://` page is enough (for
   example your repository's address). Nothing is published.
2. Save, open the profile's **Web Settings** and note its **Client ID** (it starts with
   `amzn1.application-oa2-client.`) and **Client Secret**.
3. In the skill, open **Account Linking** and fill in:
   - **Authorization URI:** `https://www.amazon.com/ap/oa`
   - **Access Token URI:** `https://api.amazon.com/auth/o2/token`
   - **Client ID** and **Client Secret:** the security profile pair from step 2. The secret is required.
   - **Authentication Scheme:** HTTP Basic
   - **Scope:** `profile` (exactly, lowercase)
4. Save. The page then lists the **Alexa Redirect URLs**. Copy all of them into the security profile,
   Web Settings, **Allowed Return URLs**, one per line, and save.
5. Wait a minute or two, then open the Alexa app on your phone, find the skill under Skills
   (Developer tab), and enable it. Sign in with Amazon when asked. Alexa then sends an `AcceptGrant`
   directive; the Lambda exchanges the code for tokens and stores them in the `robot-tokens` table.
   Do this only after the deploy in step 5, because the Lambda must exist to answer.
6. Check that the token was stored, without printing it:

   ```
   aws dynamodb scan --table-name robot-tokens --select COUNT --profile robot --region us-east-1
   ```

   It should report `"Count": 1`.
7. Say "Alexa, discover devices" (or add a device in the app: Devices, Add device, Other, Discover).
   A device named **PC**, category Computer, should appear.

If enabling the skill fails with **400 Bad Request**, the Login with Amazon request was refused before
it reached your Lambda. Check the Allowed Return URLs first, then the client id and secret (they must be
the security profile pair), then the URIs and the scope. If it fails after you sign in with "could not
link your account", the problem is the `AcceptGrant` in the Lambda: check you gave `sam deploy` the
Permissions tab pair, that Send Alexa Events is on, and read the Lambda logs.

## 7. Test "turn on"

Shut the PC down completely, then say:

> "Alexa, turn on the PC"  (in Portuguese: "Alexa, ligar o PC")

The PC should power on. If the phone test in step 2 worked but this does not, check the Lambda logs in
CloudWatch (`/aws/lambda/robot-lambda`). The logs never contain tokens, secrets or event bodies.

"PC" is the device name on purpose: in Portuguese, "computador" is an Alexa wake word.

## 8. Install the agent and test "turn off"

1. Create the agent's access key. The secret is shown only once, so keep the terminal open:

   ```
   aws iam create-access-key --user-name robot-agente --profile robot
   ```

2. On the PC, from the `agent` folder, store the key and the queue URL (the secret is typed hidden and
   goes to the Windows Credential Manager, never to a file):

   ```
   python -m robot_agent.configure
   ```

3. Test in the foreground and watch `%LOCALAPPDATA%\robot-agente\agent.log`, then register the
   scheduled task from an administrator PowerShell. Full steps, the logon trigger and removal are in
   `agent/README.md`.
4. **Save your work first.** Say "Alexa, turn off the PC". Windows warns and shuts down after 30
   seconds (`shutdown /a` cancels).

The agent only runs a fixed list of actions (today just `shutdown`) and never executes text from the
queue.

## 9. Check everything

```
python scripts/verify.py --full
```

The tests use no network or AWS and never shut a machine down. They do not exercise Alexa,
Wake-on-LAN or the deployed Lambda; those are the manual tests above. The manual acceptance
checklist is in `infra/README.md`.

## Costs

The target is zero, using Lambda, SQS, a small DynamoDB table and CloudWatch Logs. The project owner
used a new AWS account with the free plan and starting credits, which expire. Whether the always-free
tier covers Lambda, SQS and DynamoDB on new accounts was **not verified**. Keep the budget alert and
check the current AWS pricing pages before relying on "free".

## Known limitations you should read before installing

- **Only you can use your skill.** A skill in development mode is visible only to the Amazon account
  that owns it. Every person who wants this needs their own AWS stack, skill and Echo. Publishing the
  skill would change the security assumptions below.
- **Turn off is fire and forget.** Alexa says "ok" even if the agent is stopped or the PC is already
  off. A stale command expires from the queue after 60 seconds.
- **The agent starts at logon, not at boot,** if Windows Task Scheduler refuses to store your account
  password (for example with a PIN or Windows Hello only account). On the login screen, turning off by
  voice will not work.
- **Long-lived agent key.** It can only read and delete messages from the queue; the worst a stolen key
  can do is stop a shutdown.
- **Anyone with `sqs:SendMessage` or `lambda:InvokeFunction` in your AWS account can trigger the
  actions.** Fine for a personal account; revisit before sharing it.
- The Lambda parameters are environment variables, visible to anyone with console access to the account.

More in `infra/README.md` and `agent/README.md`.

## Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| The Alexa console rejects the Lambda ARN | The invoke permission must use the principal `alexa-connectedhome.amazon.com` with your Skill ID as the token. The SAM `AlexaSkill` event uses the custom-skill principal and does not work. This template already does it correctly. |
| Enabling the skill gives 400 Bad Request, or "could not link your account" | See the end of step 6. The first is usually the Allowed Return URLs; the second is usually the wrong client pair given to `sam deploy`. |
| Account linking succeeds but "turn on" does nothing | `AcceptGrant` failed. Check you used the **Permissions tab** client id and secret for the deploy, not the account-linking ones. Check CloudWatch. |
| Phone Wake-on-LAN works, voice does not | The Echo must be on the same network as the PC and the skill must be enabled; re-run device discovery. |
| Agent log shows HTTP 403 | The PC clock is off by more than a few minutes; fix the time. |
| `sam deploy` fails on IAM | The `--capabilities CAPABILITY_NAMED_IAM` flag is missing. |
| Scheduled task will not register | Task Scheduler refused the password. Use `-Trigger Logon` (see `agent/README.md`). |

## Removing everything

Delete the CloudFormation stack (`sam delete --region us-east-1 --profile robot`), delete the skill in
the Alexa console, and on the PC run `Unregister-ScheduledTask -TaskName RobotAgente -Confirm:$false`
and `cmdkey /delete:robot-agente`.
