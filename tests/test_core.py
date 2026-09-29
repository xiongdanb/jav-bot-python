import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx

from app import database
from app.javbus import FetchError, InvalidCodeError, _request, _validate_target, extract_value, normalize_code


class ParsingTests(unittest.TestCase):
    def test_normalize_code_variants(self):
        self.assertEqual(normalize_code("ssis001"), "SSIS-001")
        self.assertEqual(normalize_code("SSIS_001"), "SSIS-001")
        self.assertEqual(normalize_code("SSIS 001"), "SSIS-001")

    def test_normalize_rejects_invalid_code(self):
        with self.assertRaises(InvalidCodeError):
            normalize_code("SSIS-001 extra")

    def test_extract_ajax_value(self):
        self.assertEqual(extract_value("var gid = 123;", "gid"), "123")
        self.assertEqual(extract_value("var img = '/cover.jpg';", "img"), "/cover.jpg")


class RequestSafetyTests(unittest.IsolatedAsyncioTestCase):
    async def test_connect_uses_validated_ip_and_original_tls_name(self):
        requests = []

        async def handler(request):
            requests.append(request)
            return httpx.Response(200, content=b"ok", request=request)

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport, trust_env=False) as client:
            with (
                patch("app.javbus._validate_target", new=AsyncMock(return_value=["93.184.216.34"])),
                patch("app.javbus.acquire_upstream_request_slot", new=AsyncMock(return_value=0)),
            ):
                response = await _request(client, "https://site.example/page")

        self.assertEqual(response.text, "ok")
        self.assertEqual(requests[0].url.host, "93.184.216.34")
        self.assertEqual(requests[0].headers["host"], "site.example")
        self.assertEqual(requests[0].extensions["sni_hostname"], b"site.example")

    async def test_redirect_is_revalidated_and_re_pinned(self):
        requests = []

        async def handler(request):
            requests.append(request)
            if len(requests) == 1:
                return httpx.Response(
                    302,
                    headers={"Location": "https://cdn.example/image"},
                    request=request,
                )
            return httpx.Response(200, content=b"image", request=request)

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler), trust_env=False
        ) as client:
            with (
                patch(
                    "app.javbus._validate_target",
                    new=AsyncMock(side_effect=[["93.184.216.34"], ["1.1.1.1"]]),
                ),
                patch("app.javbus.acquire_upstream_request_slot", new=AsyncMock(return_value=0)),
            ):
                response = await _request(client, "https://site.example/start")

        self.assertEqual(response.text, "image")
        self.assertEqual(requests[1].url.host, "1.1.1.1")
        self.assertEqual(requests[1].headers["host"], "cdn.example")
        self.assertEqual(requests[1].extensions["sni_hostname"], b"cdn.example")

    async def test_response_body_limit_is_enforced_while_streaming(self):
        class ChunkStream(httpx.AsyncByteStream):
            async def __aiter__(self):
                yield b"12"
                yield b"34"

            async def aclose(self):
                return None

        async def handler(request):
            return httpx.Response(200, stream=ChunkStream(), request=request)

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler), trust_env=False
        ) as client:
            with (
                patch("app.javbus._validate_target", new=AsyncMock(return_value=["93.184.216.34"])),
                patch("app.javbus.acquire_upstream_request_slot", new=AsyncMock(return_value=0)),
            ):
                with self.assertRaises(FetchError):
                    await _request(client, "https://site.example/page", max_bytes=3)

    async def test_private_dns_result_is_rejected(self):
        class FakeLoop:
            async def getaddrinfo(self, *args, **kwargs):
                return [(0, 0, 0, "", ("127.0.0.1", 443))]

        with patch("app.javbus.asyncio.get_running_loop", return_value=FakeLoop()):
            with self.assertRaises(FetchError):
                await _validate_target("https://www.javbus.com/")


class SQLiteCoordinationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_path = database.DATABASE_PATH
        database.DATABASE_PATH = str(Path(self.temp_dir.name) / "test.db")
        await database.init_db()

    async def asyncTearDown(self):
        database.DATABASE_PATH = self.original_path
        self.temp_dir.cleanup()

    async def test_user_cooldown_is_persisted(self):
        self.assertTrue(await database.acquire_query_cooldown(1, 2, 30))
        self.assertFalse(await database.acquire_query_cooldown(1, 2, 30))
        self.assertTrue(await database.acquire_query_cooldown(9, 2, 30))

    async def test_global_request_quota_is_shared_in_sqlite(self):
        self.assertEqual(await database.acquire_upstream_request_slot(1), 0)
        self.assertGreater(await database.acquire_upstream_request_slot(1), 0)


if __name__ == "__main__":
    unittest.main()
