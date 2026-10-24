"""Offline regressions: no Twitch credentials, requests, or video downloads."""
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from channel import Channel, Stream
from constants import WATCH_INTERVAL
with patch.object(sys, 'argv', [sys.argv[0], '--web']):
    from twitch import Twitch
from yarl import URL


def media(*segments):
    return '#EXTM3U\n' + ''.join(f'#EXTINF:2,\n{s}\n' for s in segments)


class MiningWatchTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.calls = []
        self.responses = []
        self.selected = None
        self.client = SimpleNamespace(
            gui_enabled=False, settings=SimpleNamespace(available_drops_check=False),
            watching_channel=SimpleNamespace(get_with_default=lambda default: self.selected),
            gql_request=AsyncMock(return_value={'data': {'streamPlaybackAccessToken': {
                'value': 'a&b=+?', 'signature': 'sig'}}}),
            request=self.request,
        )
        self.channel = Channel(self.client, id=1, login='example')
        self.selected = self.channel
        self.stream = Stream(self.channel, id=10, game=None, viewers=1, title='test')
        self.channel._stream = self.stream
        self.stream._stream_url = URL('https://cdn.example/live/index.m3u8')

    @asynccontextmanager
    async def request(self, method, url, **kwargs):
        self.calls.append((method, str(url)))
        status, text, callback = self.responses.pop(0)
        if callback:
            await callback()
        yield SimpleNamespace(status=status, text=AsyncMock(return_value=text), url=URL(url))

    def reply(self, text='', status=200, callback=None):
        self.responses.append((status, text, callback))

    async def test_playlist_heads_each_new_segment_only(self):
        self.reply(media('a.ts', 'b.ts') + '#EXT-X-ENDLIST\n')
        self.reply()
        self.reply()
        self.assertTrue(await self.channel.send_watch())
        self.reply(media('a.ts', 'b.ts', 'c.ts'))
        self.reply()
        self.assertTrue(await self.channel.send_watch())
        self.assertEqual([url for method, url in self.calls if method == 'HEAD'], [
            'https://cdn.example/live/a.ts', 'https://cdn.example/live/b.ts',
            'https://cdn.example/live/c.ts'])
        self.assertTrue(all(method in ('GET', 'HEAD') for method, _ in self.calls))
        self.reply(media('a.ts', 'b.ts', 'c.ts'))
        self.assertFalse(await self.channel.send_watch())

    async def test_failed_segment_retried_not_successes(self):
        self.reply(media('a.ts', 'b.ts'))
        self.reply()
        self.reply(status=404)
        await self.channel.send_watch()
        self.reply(media('a.ts', 'b.ts'))
        self.reply()
        self.assertTrue(await self.channel.send_watch())
        self.assertEqual([u for m, u in self.calls if m == 'HEAD'], [
            'https://cdn.example/live/a.ts', 'https://cdn.example/live/b.ts',
            'https://cdn.example/live/b.ts'])

    async def test_expired_playlist_refreshes_token_next_tick(self):
        for status in (401, 403, 404, 410):
            with self.subTest(status=status):
                self.stream._stream_url = URL('https://cdn.example/expired.m3u8')
                self.reply(status=status)
                self.assertFalse(await self.channel.send_watch())
                self.assertIsNone(self.stream._stream_url)
                self.reply('#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=100\nhttps://cdn.example/new.m3u8\n# trailing comment\n')
                self.reply(media('https://cdn.example/fresh' + str(status) + '.ts'))
                self.reply()
                self.assertTrue(await self.channel.send_watch())
                usher = next(URL(u) for m, u in reversed(self.calls) if 'usher.ttvnw.net' in u)
                self.assertEqual(usher.query['token'], 'a&b=+?')

    async def test_invalid_playlists_never_become_segment_requests(self):
        for text in ('', '[]', '{}', 'null', '42', '<html>bad</html>', '#EXTM3U\n#EXT-X-ENDLIST',
                     '#EXTM3U\n#EXTINF:2,\nfile:///bad', '#EXTM3U\nhttps://cdn.example/no-extinf'):
            with self.subTest(text=text):
                self.stream._stream_url = URL('https://cdn.example/live/index.m3u8')
                self.reply(text)
                self.assertFalse(await self.channel.send_watch())
        self.assertTrue(all(m == 'GET' for m, _ in self.calls))

    async def test_invalid_master_and_token_fail_safely(self):
        for text in ('', '[]', '{}', 'null', '<html>bad</html>', '#EXTM3U\n#EXT-X-ENDLIST'):
            self.stream._stream_url = None
            self.reply(text)
            self.assertFalse(await self.channel.send_watch())
        self.client.gql_request.return_value = {'data': {'streamPlaybackAccessToken': None}}
        self.assertFalse(await self.channel.send_watch())

    async def test_offline_or_switched_during_request_stops_heads(self):
        async def offline():
            self.channel._stream = None
        self.reply(media('a.ts'), callback=offline)
        self.assertFalse(await self.channel.send_watch())
        self.channel._stream = self.stream
        async def switch():
            self.selected = object()
        self.reply(media('b.ts'), callback=switch)
        self.assertFalse(await self.channel.send_watch())
        self.assertTrue(all(m == 'GET' for m, _ in self.calls))

    async def test_cancel_propagates(self):
        async def cancel():
            raise asyncio.CancelledError
        self.reply(media('a.ts'), callback=cancel)
        with self.assertRaises(asyncio.CancelledError):
            await self.channel.send_watch()

    async def test_total_watch_wait_is_bounded(self):
        async def hang():
            await asyncio.Event().wait()
        self.reply(callback=hang)
        with patch('channel.WATCH_REQUEST_TIMEOUT', 0.01, create=True):
            self.assertFalse(await asyncio.wait_for(self.channel.send_watch(), 0.5))

    async def test_token_and_head_waits_are_bounded(self):
        async def hang(*args, **kwargs):
            await asyncio.Event().wait()
        with patch('channel.WATCH_REQUEST_TIMEOUT', 0.01):
            self.stream._stream_url = None
            self.client.gql_request.side_effect = hang
            self.assertFalse(await asyncio.wait_for(self.channel.send_watch(), 0.5))
            self.stream._stream_url = URL('https://cdn.example/live/index.m3u8')
            self.reply(media('a.ts', 'b.ts'))
            self.reply()
            self.reply(callback=hang)
            self.assertFalse(await asyncio.wait_for(self.channel.send_watch(), 0.5))
            self.reply(media('a.ts', 'b.ts'))
            self.reply()
            self.assertTrue(await self.channel.send_watch())
        self.assertEqual(sum(m == 'HEAD' and u.endswith('/a.ts') for m, u in self.calls), 1)

    async def test_shutdown_propagates_and_transient_errors_do_not(self):
        from exceptions import ExitRequest, GQLException, RequestException
        for error in (RequestException(), GQLException('unavailable'), ExitRequest()):
            async def fail():
                raise error
            self.reply(callback=fail)
            if isinstance(error, ExitRequest):
                with self.assertRaises(ExitRequest):
                    await self.channel.send_watch()
            else:
                self.assertFalse(await self.channel.send_watch())

    async def test_stale_stream_during_head_stops_remaining_batch(self):
        async def replace():
            self.channel._stream = Stream(self.channel, id=11, game=None, viewers=1, title='new')
        self.reply(media('a.ts', 'b.ts'))
        self.reply(callback=replace)
        self.assertFalse(await self.channel.send_watch())
        self.assertEqual(sum(m == 'HEAD' for m, _ in self.calls), 1)

    async def test_history_has_bounded_memory(self):
        from channel import WATCH_SEGMENT_HISTORY
        for start in range(0, WATCH_SEGMENT_HISTORY + 16, 16):
            self.reply(media(*(f'{i}.ts' for i in range(start, start + 16))))
            for _ in range(16):
                self.reply()
            self.assertTrue(await self.channel.send_watch())
        self.assertEqual(len(self.stream._watched_segments), WATCH_SEGMENT_HISTORY)

    async def test_real_http_transport_uses_head_not_video_get(self):
        import aiohttp
        from aiohttp import web
        from constants import State
        methods = []
        async def handler(request):
            methods.append((request.method, request.path))
            if request.path == '/index.m3u8':
                return web.Response(text=media('segment.ts'))
            self.assertEqual(request.method, 'HEAD')
            return web.Response(headers={'Content-Length': '1000000'})
        app = web.Application()
        app.router.add_route('*', '/{path}', handler)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '127.0.0.1', 0)
        await site.start()
        try:
            port = site._server.sockets[0].getsockname()[1]
            async with aiohttp.ClientSession() as session:
                self.client.get_session = AsyncMock(return_value=session)
                self.client.settings.proxy = None
                self.client._state = State.IDLE
                self.client.request = lambda *args, **kwargs: Twitch.request(self.client, *args, **kwargs)
                self.stream._stream_url = URL(f'http://127.0.0.1:{port}/index.m3u8')
                self.assertTrue(await self.channel.send_watch())
                self.assertFalse(await self.channel.send_watch())
            self.assertEqual(methods, [('GET', '/index.m3u8'), ('HEAD', '/segment.ts'), ('GET', '/index.m3u8')])
        finally:
            await runner.cleanup()

    async def test_metadata_refresh_preserves_dedup_but_new_broadcast_does_not(self):
        self.reply(media('a.ts'))
        self.reply()
        self.assertTrue(await self.channel.send_watch())
        refreshed = Stream(self.channel, id=10, game=None, viewers=2, title='new title')
        self.channel._stream = refreshed
        self.reply(media('a.ts'))
        self.assertFalse(await self.channel.send_watch())
        new = Stream(self.channel, id=11, game=None, viewers=2, title='new broadcast')
        self.assertIsNone(new._stream_url)
        self.assertFalse(new._watched_segments)


class WatchLoopTests(unittest.IsolatedAsyncioTestCase):
    async def run_loop(self, gui=False, switch=False):
        clock = [1000.0]
        polls = []
        selected = [None]
        channel = SimpleNamespace(id=1, name='test', online=True, send_watch=AsyncMock(return_value=True))
        selected[0] = channel
        async def sleep(delay):
            clock[0] += delay
            if switch:
                selected[0] = object()
        async def pause(delay):
            clock[0] += delay
            if clock[0] >= 1260:
                raise asyncio.CancelledError
        async def query(op):
            polls.append(clock[0])
            return {'data': {'currentUser': {'dropCurrentSession': None}}}
        client = SimpleNamespace(
            watching_channel=SimpleNamespace(get=AsyncMock(return_value=channel),
                get_with_default=lambda default: selected[0]),
            gui_enabled=gui, gui=SimpleNamespace(progress=SimpleNamespace(minute_almost_done=lambda: True)),
            gql_request=query, get_active_campaign=lambda channel: None, _watch_sleep=pause,
        )
        with patch('twitch.time', side_effect=lambda: clock[0]), \
             patch('twitch.monotonic', side_effect=lambda: clock[0], create=True), \
             patch('twitch.asyncio.sleep', side_effect=sleep):
            with self.assertRaises(asyncio.CancelledError):
                await Twitch._watch_loop.__wrapped__(client)
        return polls

    async def test_skipped_ticks_do_not_starve_authoritative_poll(self):
        for gui in (False, True):
            polls = await self.run_loop(gui=gui)
            self.assertGreaterEqual(len(polls), 3)
            self.assertTrue(all(60 < b - a <= 100 for a, b in zip(polls, polls[1:])))

    async def test_switched_channel_not_polled_after_wait(self):
        self.assertEqual(await self.run_loop(switch=True), [])

    def test_playlist_cadence(self):
        self.assertEqual(WATCH_INTERVAL.total_seconds(), 20)


if __name__ == '__main__':
    unittest.main()
