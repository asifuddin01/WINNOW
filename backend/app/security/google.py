"""Sign in with Google: OpenID Connect (app.security.oidc) with PKCE on top.

PKCE makes an intercepted code useless. Google must also have verified the email address,
because a Winnow account with that address is linked to it.
"""

from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

from app.security.oidc import OidcClient, SignInError

AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"  # noqa: S105 - an endpoint, not a secret
JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
ISSUERS = ("https://accounts.google.com", "accounts.google.com")
PROVIDER = "google"


@dataclass(frozen=True, slots=True)
class GoogleProfile:
    subject: str
    email: str
    name: str


def authorization_url(
    client_id: str, redirect_uri: str, state: str, nonce: str, code_challenge: str
) -> str:
    return (
        AUTHORIZE_URL
        + "?"
        + urlencode(
            {
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "scope": "openid email profile",
                "state": state,
                "nonce": nonce,
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
                "prompt": "select_account",
            }
        )
    )


class GoogleClient(OidcClient):
    provider = PROVIDER

    def __init__(self, http: httpx.AsyncClient, client_id: str, client_secret: str) -> None:
        super().__init__(
            http, client_id, client_secret, token_url=TOKEN_URL, jwks_url=JWKS_URL, issuers=ISSUERS
        )

    async def verify(self, id_token: str, nonce: str) -> GoogleProfile:
        """Check the token and require an email address Google has verified."""
        claims = await self.claims(id_token, nonce)
        email = claims.get("email")
        if not isinstance(email, str) or claims.get("email_verified") is not True:
            raise SignInError("google_unverified")
        name = claims.get("name")
        return GoogleProfile(
            subject=str(claims["sub"]),
            email=email,
            name=name if isinstance(name, str) and name.strip() else email.split("@")[0],
        )
