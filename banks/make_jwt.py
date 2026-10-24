"""Print a 1h Enable Banking JWT for one application.

Usage: make_jwt.py APP_ID. Each bank has its own
Enable Banking application; its private key is <APP_ID>.pem next to this file
(override with PRIVATE_KEY_PATH for one-off runs).
"""
import jwt
import os
import time
import sys

if len(sys.argv) != 2:
    sys.exit("usage: make_jwt.py APP_ID")
APPLICATION_ID = sys.argv[1]
PRIVATE_KEY_PATH = os.environ.get(
    "PRIVATE_KEY_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), f"{APPLICATION_ID}.pem"),
)

with open(PRIVATE_KEY_PATH) as f:
    private_key = f.read()

iat = int(time.time())
payload = {
    "iss": "enablebanking.com",
    "aud": "api.enablebanking.com",
    "iat": iat,
    "exp": iat + 3600,  # valid for 1 h
}
headers = {
    "typ": "JWT",
    "alg": "RS256",
    "kid": APPLICATION_ID,
}

token = jwt.encode(payload, private_key, algorithm="RS256", headers=headers)
print(token)