"""Initial configuration: python -m robot_agent.configure

Asks for the queue URL and the access key of the robot-agente user. The secret is typed without
echo and goes straight to the Credential Manager: it never touches a file or the terminal history.
"""
from __future__ import annotations

import getpass
import re
import sys

from . import config
from .adapters import credentials
from .adapters.sqs import region_from_url
from .errors import AgentError

ID_FORMAT = re.compile(r"^[A-Z0-9]{16,32}$")
# AWS secrets are 40 base64 characters. Ctrl+V in a hidden Windows prompt types a control
# character instead of pasting, so anything else is refused here instead of failing later with HTTP 403.
SECRET_FORMAT = re.compile(r"^[A-Za-z0-9/+=]{30,128}$")


def main() -> int:
    try:
        url = input("Queue URL (QueueUrl output of sam deploy): ").strip()
        region_from_url(url)
        key_id = input("Access key ID of robot-agente: ").strip()
        if not ID_FORMAT.match(key_id):
            print("Key ID outside the expected format.")
            return 2
        secret = getpass.getpass("Key secret (not shown on screen): ").strip()
        if not secret:
            print("Empty secret.")
            return 2
        if not SECRET_FORMAT.match(secret):
            print("Secret outside the expected format. Paste it with a right click, not Ctrl+V.")
            return 2
        credentials.write(key_id, secret)
        file = config.write_queue_url(url)
    except AgentError as error:
        print(f"Not configured: {error}")
        return 2
    print(f"Credential saved in the Credential Manager (target '{credentials.TARGET}').")
    print(f"Queue URL saved in {file}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
