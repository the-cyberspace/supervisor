"""Home Assistant Websocket API."""
import logging
from typing import Optional

import aiohttp

from ..coresys import CoreSys, CoreSysAttributes
from ..exceptions import HomeAssistantAPIError, HomeAssistantWSError

_LOGGER: logging.Logger = logging.getLogger(__name__)


class HomeAssistantWS(CoreSysAttributes):
    """Home Assistant Websocket API."""

    def __init__(self, coresys: CoreSys):
        """Initialize Home Assistant object."""
        self.coresys: CoreSys = coresys
        self._client: Optional["WSClient"] = None

    async def _get_ws_client(self) -> "WSClient":
        """Return a websocket client."""
        await self.sys_homeassistant.api.ensure_access_token()
        return await WSClient.connect_with_auth(
            self.sys_websession_ssl,
            f"{self.sys_homeassistant.api_url}/api/websocket",
            self.sys_homeassistant.api.access_token,
        )

    async def send_command(self, msg):
        """Send a command with the WS client."""
        if not self._client:
            self._client = await self._get_ws_client()
        try:
            return await self._client.send_command(msg)
        except HomeAssistantAPIError as err:
            raise HomeAssistantWSError from err


class WSClient:
    """Home Assistant Websocket client."""

    def __init__(self, ha_version: str, client: aiohttp.ClientWebSocketResponse):
        """Initialise the WS client."""
        self.ha_version = ha_version
        self.client = client
        self.msg_id = 0

    async def send_command(self, msg):
        """Send a websocket command."""
        self.msg_id += 1
        msg["id"] = self.msg_id
        _LOGGER.debug("Sending command %s", msg)

        await self.client.send_json(msg)

        response = await self.client.receive_json()

        _LOGGER.debug("Received command %s", response)

        if response["success"]:
            return response["result"]

        raise HomeAssistantWSError(response)

    @classmethod
    async def connect_with_auth(
        cls, session: aiohttp.ClientSession, url: str, token: str
    ) -> aiohttp.ClientWebSocketResponse:
        """Create an authenticated websocket client."""
        try:
            client = await session.ws_connect(url)
        except aiohttp.client_exceptions.ClientConnectorError:
            raise HomeAssistantWSError("Can't connect") from None

        hello_msg = await client.receive_json()

        _LOGGER.debug("Received msg: %s", hello_msg)

        _LOGGER.debug("Sending token")
        await client.send_json({"type": "auth", "access_token": token})

        auth_ok_msg = await client.receive_json()

        _LOGGER.debug("Received msg: %s", auth_ok_msg)

        if auth_ok_msg["type"] != "auth_ok":
            raise HomeAssistantAPIError("AUTH NOT OK")

        return cls(hello_msg["ha_version"], client)
