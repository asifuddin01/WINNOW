"""Sign in with ORCID: OpenID Connect (app.security.oidc) against orcid.org.

ORCID does not offer PKCE; the nonce, checked in the ID token, is what ties the code to the
sign-in this browser started. ORCID shares no email address, so an iD only signs in to an
account it has been linked to from that account (docs/decisions.md).
"""

import re
from urllib.parse import urlencode

import httpx

from app.security.oidc import OidcClient

PROVIDER = "orcid"
_ORCID_ID = re.compile(r"\d{4}-\d{4}-\d{4}-\d{3}[\dX]")


def authorization_url(
    base_url: str, client_id: str, redirect_uri: str, state: str, nonce: str
) -> str:
    return f"{base_url}/oauth/authorize?" + urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid",
            "state": state,
            "nonce": nonce,
        }
    )


class OrcidClient(OidcClient):
    provider = PROVIDER

    def __init__(
        self, http: httpx.AsyncClient, client_id: str, client_secret: str, base_url: str
    ) -> None:
        super().__init__(
            http,
            client_id,
            client_secret,
            token_url=f"{base_url}/oauth/token",
            jwks_url=f"{base_url}/oauth/jwks",
            issuers=(base_url,),
        )

    async def verify(self, id_token: str, nonce: str) -> str:
        """Check the token, and return its subject: the person's ORCID iD."""
        claims = await self.claims(id_token, nonce)
        orcid = str(claims["sub"])
        if not _ORCID_ID.fullmatch(orcid):
            raise self.failed()
        return orcid
