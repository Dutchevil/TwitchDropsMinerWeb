from __future__ import annotations

import re
import gzip
from collections import deque
import asyncio
import logging
from base64 import b64encode
from functools import cached_property
from typing import Any, SupportsInt, cast, TYPE_CHECKING

import aiohttp
from yarl import URL

from utils import Game, json_minify, isonow
from exceptions import MinerException, RequestException
from constants import CALL, GQL_QUERIES, ONLINE_DELAY, URLType, GQLQuery

if TYPE_CHECKING:
    from twitch import Twitch
    from gui import ChannelList
    from constants import JsonType, GQLPersistedQuery


logger = logging.getLogger("TwitchDrops")

# Bound the entire token/playlist/HEAD operation, including request()'s retry backoff.
WATCH_REQUEST_TIMEOUT = 15
WATCH_SEGMENT_HISTORY = 256


def _playlist_urls(text: str, base: URL, tag: str) -> list[URLType]:
    """Read URI lines belonging to HLS entries, not comments/keys/error bodies."""
    lines = text.lstrip("\ufeff").strip().splitlines()
    if not lines or lines[0].strip() != "#EXTM3U":
        return []
    urls = []
    pending = False
    for raw_line in lines[1:]:
        line = raw_line.strip()
        if line.startswith(tag):
            pending = True
        elif not line or line.startswith("#"):
            continue
        else:
            if pending:
                try:
                    url = base.join(URL(line))
                    if url.scheme in ("http", "https") and url.host and not url.user:
                        urls.append(cast(URLType, url))
                except ValueError:
                    pass
            pending = False
    return urls


class Stream:
    def __init__(
        self,
        channel: Channel,
        *,
        id: SupportsInt,
        game: JsonType | None,
        viewers: int,
        title: str,
    ):
        self.channel: Channel = channel
        self.broadcast_id = int(id)
        self.viewers: int = viewers
        self.drops_enabled: bool = not channel._twitch.settings.available_drops_check
        self.game: Game | None = Game(game) if game else None
        self.title: str = title
        self._stream_url: URLType | None = None
        self._watched_segments: deque[URLType] = deque(maxlen=WATCH_SEGMENT_HISTORY)
        previous = channel._stream
        if previous is not None and previous.broadcast_id == self.broadcast_id:
            # Metadata refreshes must not replay the same broadcast's segments.
            self._stream_url = previous._stream_url
            self._watched_segments = previous._watched_segments

    @cached_property
    def _watch_payload(self) -> list[JsonType]:
        return [
            {
                "event": "minute-watched",
                "properties": {
                    "broadcast_id": str(self.broadcast_id),
                    "channel_id": str(self.channel.id),
                    "channel": self.channel._login,
                    "client_time": isonow(),
                    "game": self.game.name if self.game is not None else "",
                    "game_id": str(self.game.id) if self.game is not None else "",
                    "hidden": False,
                    "is_live": True,
                    "live": True,
                    "logged_in": True,
                    "minutes_logged": 1,
                    "muted": False,
                    "user_id": self.channel._twitch._auth_state.user_id,
                }
            }
        ]

    @cached_property
    def spade_payload(self) -> JsonType:
        return {"data": (b64encode(json_minify(self._watch_payload).encode("utf8"))).decode("utf8")}

    @cached_property
    def gql_payload(self) -> GQLQuery:
        return GQLQuery(
            (
                "\n mutation SendEvents($input: SendSpadeEventsInput!) "
                "{\n sendSpadeEvents(input: $input) {\n statusCode\n}\n}\n"
            ),
            b64encode(gzip.compress(json_minify(self._watch_payload).encode("utf8"))).decode("utf8")
        )

    @classmethod
    def from_get_stream(cls, channel: Channel, channel_data: JsonType) -> Stream:
        stream = channel_data["stream"]
        settings = channel_data["broadcastSettings"]
        return cls(
            channel,
            id=stream["id"],
            game=settings["game"],
            viewers=stream["viewersCount"],
            title=settings["title"],
        )

    @classmethod
    def from_directory(
        cls, channel: Channel, channel_data: JsonType, *, drops_enabled: bool = False
    ) -> Stream:
        self = cls(
            channel,
            id=channel_data["id"],
            game=channel_data["game"],  # has to be there since we searched with it
            viewers=channel_data["viewersCount"],
            title=channel_data["title"],
        )
        self.drops_enabled = drops_enabled
        return self

    def __eq__(self, other: object) -> bool:
        if isinstance(other, self.__class__):
            return self.broadcast_id == other.broadcast_id
        return NotImplemented

    async def get_stream_url(self) -> URLType | None:
        if self._stream_url is not None:
            return self._stream_url
        response = await self.channel._twitch.gql_request(
            GQL_QUERIES["PlaybackAccessToken"].with_variables({"login": self.channel._login})
        )
        data = response.get("data") if isinstance(response, dict) else None
        token = data.get("streamPlaybackAccessToken") if isinstance(data, dict) else None
        if not isinstance(token, dict) or not all(
            isinstance(token.get(key), str) and token[key] for key in ("value", "signature")
        ):
            return None
        usher_url = URL(
            f"https://usher.ttvnw.net/api/channel/hls/{self.channel._login}.m3u8"
        ).with_query(sig=token["signature"], token=token["value"])
        async with self.channel._twitch.request("GET", usher_url) as response:
            if response.status != 200:
                return None
            qualities = _playlist_urls(await response.text(), response.url, "#EXT-X-STREAM-INF:")
        if qualities:
            # Twitch orders variants highest to lowest quality.
            self._stream_url = qualities[-1]
        return self._stream_url


class Channel:
    __slots__ = (
        "_twitch", "_gui_channels", "id", "_login", "_display_name", "_spade_url",
        "_stream", "_pending_stream_up", "acl_based"
    )

    def __init__(
        self,
        twitch: Twitch,
        *,
        id: SupportsInt,
        login: str,
        display_name: str | None = None,
        acl_based: bool = False,
    ):
        self._twitch: Twitch = twitch
        if self._twitch.gui_enabled:
            self._gui_channels: ChannelList = twitch.gui.channels
        self.id: int = int(id)
        self._login: str = login
        self._display_name: str | None = display_name
        self._spade_url: URLType | None = None
        self._stream: Stream | None = None
        self._pending_stream_up: asyncio.Task[Any] | None = None
        # ACL-based channels are:
        # • considered first when switching channels
        # • if we're watching a non-based channel, a based channel going up triggers a switch
        # • not cleaned up unless they're streaming a game we haven't selected
        self.acl_based: bool = acl_based

    @classmethod
    def from_acl(cls, twitch: Twitch, data: JsonType) -> Channel:
        return cls(
            twitch,
            id=data["id"],
            login=data["name"],
            display_name=data.get("displayName"),
            acl_based=True,
        )

    @classmethod
    def from_directory(
        cls, twitch: Twitch, data: JsonType, *, drops_enabled: bool = False
    ) -> Channel:
        channel = data["broadcaster"]
        self = cls(
            twitch, id=channel["id"], login=channel["login"], display_name=channel["displayName"]
        )
        self._stream = Stream.from_directory(self, data, drops_enabled=drops_enabled)
        return self

    def __repr__(self) -> str:
        if self._display_name is not None:
            name = f"{self._display_name}({self._login})"
        else:
            name = self._login
        return f"Channel({name}, {self.id})"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, self.__class__):
            return self.id == other.id
        return NotImplemented

    def __hash__(self) -> int:
        return self.id

    @property
    def stream_gql(self) -> GQLPersistedQuery:
        return GQL_QUERIES["GetStreamInfo"].with_variables({"channel": self._login})

    @property
    def name(self) -> str:
        if self._display_name is not None:
            return self._display_name
        return self._login

    @property
    def url(self) -> URLType:
        return URLType(f"{self._twitch._client_type.CLIENT_URL}/{self._login}")

    @property
    def iid(self) -> str:
        """
        Returns a string to be used as ID/key of the columns inside channel list.
        """
        return str(self.id)

    @property
    def online(self) -> bool:
        """
        Returns True if the streamer is online and is currently streaming, False otherwise.
        """
        return self._stream is not None

    @property
    def offline(self) -> bool:
        """
        Returns True if the streamer is offline and isn't about to come online, False otherwise.
        """
        return self._stream is None and self._pending_stream_up is None

    @property
    def pending_online(self) -> bool:
        """
        Returns True if the streamer is about to go online (most likely), False otherwise.
        This is because 'stream-up' event is received way before
        stream information becomes available.
        """
        return self._stream is None and self._pending_stream_up is not None

    @property
    def game(self) -> Game | None:
        if self._stream is not None:
            return self._stream.game
        return None

    @property
    def viewers(self) -> int | None:
        if self._stream is not None:
            return self._stream.viewers
        return None

    @viewers.setter
    def viewers(self, value: int):
        if self._stream is not None:
            self._stream.viewers = value

    @property
    def drops_enabled(self) -> bool:
        if self._stream is not None:
            return self._stream.drops_enabled
        return False

    def display(self, *, add: bool = False):
        if self._twitch.gui_enabled:
            self._gui_channels.display(self, add=add)

    def remove(self):
        if self._pending_stream_up is not None:
            self._pending_stream_up.cancel()
            self._pending_stream_up = None
        if self._twitch.gui_enabled:
            self._gui_channels.remove(self)

    async def get_spade_url(self) -> URLType:
        """
        To get this monstrous thing, you have to walk a chain of requests.
        Streamer page (HTML) --parse-> Streamer Settings (JavaScript) --parse-> Spade URL

        For mobile view, spade_url is available immediately from the page, skipping step #2.
        """
        SETTINGS_PATTERN: str = r'src="(https://[\w.]+/config/settings\.[0-9a-f]{32}\.js)"'
        SPADE_PATTERN: str = r'"spade_?url": ?"(https://[.\w\-/]+)"'
        async with self._twitch.request("GET", self.url) as response1:
            streamer_html: str = await response1.text(encoding="utf8")
        match = re.search(SPADE_PATTERN, streamer_html, re.I)
        if not match:
            match = re.search(SETTINGS_PATTERN, streamer_html, re.I)
            if not match:
                raise MinerException("Error while spade_url extraction: step #1")
            streamer_settings = match.group(1)
            async with self._twitch.request("GET", streamer_settings) as response2:
                settings_js: str = await response2.text(encoding="utf8")
            match = re.search(SPADE_PATTERN, settings_js, re.I)
            if not match:
                raise MinerException("Error while spade_url extraction: step #2")
        return URLType(match.group(1))

    def _check_drops_enabled(self, available_drops: list[JsonType]) -> bool:
        return any(
            (
                (campaign := self._twitch._campaigns.get(campaign_data["id"])) is not None
                and campaign.can_earn(self, ignore_channel_status=True)
            )
            for campaign_data in available_drops
        )

    def external_update(self, channel_data: JsonType, available_drops: list[JsonType]):
        """
        Update stream information based on data provided externally.

        Used for bulk-updates of channel statuses during reload.
        """
        if not channel_data["stream"]:
            self._stream = None
            return
        stream = Stream.from_get_stream(self, channel_data)
        if not stream.drops_enabled:
            stream.drops_enabled = self._check_drops_enabled(available_drops)
        self._stream = stream

    async def get_stream(self) -> Stream | None:
        try:
            response: JsonType = await self._twitch.gql_request(self.stream_gql)
        except MinerException as exc:
            raise MinerException(f"Channel: {self._login}") from exc
        channel_data: JsonType | None = response["data"]["user"]
        if not channel_data:
            return None
        # fill in display name
        if self._display_name is None:
            self._display_name = channel_data["displayName"]
        if not channel_data["stream"]:
            return None
        stream = Stream.from_get_stream(self, channel_data)
        if not stream.drops_enabled:
            try:
                available_drops_campaigns: JsonType = await self._twitch.gql_request(
                    GQL_QUERIES["AvailableDrops"].with_variables({"channelID": str(self.id)})
                )
            except MinerException:
                logger.log(CALL, f"AvailableDrops GQL call failed for channel: {self._login}")
            else:
                stream.drops_enabled = self._check_drops_enabled(
                    available_drops_campaigns["data"]["channel"]["viewerDropCampaigns"] or []
                )
        return stream

    async def update_stream(self) -> bool:
        """
        Fetches the current channel stream, and if one exists,
        updates it's game, title, tags and viewers. Updates channel status in general.
        """
        old_stream = self._stream
        self._stream = await self.get_stream()
        self._twitch.on_channel_update(self, old_stream, self._stream)
        return self._stream is not None

    async def _online_delay(self):
        """
        The 'stream-up' event is sent before the stream actually goes online,
        so just wait a bit and check if it's actually online by then.
        """
        await asyncio.sleep(ONLINE_DELAY.total_seconds())
        self._pending_stream_up = None  # for 'display' to work properly
        await self.update_stream()

    def check_online(self):
        """
        Sets up a task that will wait ONLINE_DELAY duration,
        and then check for the stream being ONLINE OR OFFLINE.

        If the channel is OFFLINE, it sets the channel's status to PENDING_ONLINE,
        where after ONLINE_DELAY, it's going to be set to ONLINE.
        If the channel is ONLINE already, after ONLINE_DELAY,
        it's status is going to be double-checked to ensure it's actually ONLINE.

        This is called externally, if we receive an event about the status possibly being ONLINE
        or having to be updated.
        """
        if self._pending_stream_up is None:
            self._pending_stream_up = asyncio.create_task(self._online_delay())
            self.display()

    def set_offline(self):
        """
        Sets the channel status to OFFLINE. Cancels PENDING_ONLINE if applicable.

        This is called externally, if we receive an event indicating the channel is now OFFLINE.
        """
        needs_display: bool = False
        if self._pending_stream_up is not None:
            self._pending_stream_up.cancel()
            self._pending_stream_up = None
            needs_display = True
        if self.online:
            old_stream = self._stream
            self._stream = None
            self._twitch.on_channel_update(self, old_stream, self._stream)
            needs_display = False  # calling on_channel_update always does a display at the end
        if needs_display:
            self.display()

    def _watch_is_current(self, stream: Stream) -> bool:
        return (
            self._stream is stream
            and self._twitch.watching_channel.get_with_default(None) is self
        )

    async def _send_watch_playlist(self) -> bool:
        stream = self._stream
        if stream is None or not self._watch_is_current(stream):
            return False
        stream_url = await stream.get_stream_url()
        if stream_url is None or not self._watch_is_current(stream):
            return False
        async with self._twitch.request(
            "GET", stream_url, headers={"Connection": "close"}
        ) as response:
            if response.status != 200:
                if response.status in (401, 403, 404, 410):
                    # Signed playlists expire. Obtain a new token on the next tick,
                    # without an unbounded refresh loop or marking the channel offline.
                    stream._stream_url = None
                return False
            segments = _playlist_urls(await response.text(), response.url, "#EXTINF:")
        if not segments:
            stream._stream_url = None
            return False
        succeeded = False
        for segment in segments:
            if not self._watch_is_current(stream):
                return False
            if segment in stream._watched_segments:
                continue
            # HEAD only: never GET a video segment. Remember successes immediately,
            # so a later failure/timeout cannot replay the successful part of a batch.
            async with self._twitch.request("HEAD", segment) as response:
                if not self._watch_is_current(stream):
                    return False
                if response.status == 200:
                    stream._watched_segments.append(segment)
                    succeeded = True
                elif response.status in (401, 403):
                    stream._stream_url = None
                    break
        return succeeded

    async def send_watch(self) -> bool:
        """Touch new HLS segments without downloading video, within one watch tick.

        A successful HEAD is transport success, not proof of Twitch drop credit.
        Cancellation and shutdown exceptions must propagate to the watch task.
        """
        try:
            return await asyncio.wait_for(self._send_watch_playlist(), WATCH_REQUEST_TIMEOUT)
        except (asyncio.TimeoutError, RequestException, aiohttp.ClientError):
            return False

    # NOTE: This is currently unused.
    async def _send_watch_gql(self) -> bool:
        if self._stream is None:
            return False
        try:
            watch_response = await self._twitch.gql_request(self._stream.gql_payload)
            return watch_response["data"]["sendSpadeEvents"]["statusCode"] == 204
        except RequestException:
            return False
