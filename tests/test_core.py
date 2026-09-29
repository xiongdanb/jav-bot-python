import tempfile
import asyncio
import shutil
import ssl
import subprocess
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx

from app import database
from app import javbus
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
        self.assertEqual(requests[0].extensions["sni_hostname"], "site.example")

    async def test_real_http_connection_uses_pinned_ip(self):
        received = asyncio.Event()
        observed = {}

        async def handle_connection(reader, writer):
            crlf = bytes((13, 10))
            request = await reader.readuntil(crlf + crlf)
            observed["request"] = request
            writer.write(crlf.join([
                b"HTTP/1.1 200 OK",
                b"Content-Length: 2",
                b"Connection: close",
                b"",
                b"ok",
            ]))
            await writer.drain()
            writer.close()
            await writer.wait_closed()
            received.set()

        server = await asyncio.start_server(handle_connection, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        try:
            async with httpx.AsyncClient(trust_env=False) as client:
                with (
                    patch("app.javbus._validate_target", new=AsyncMock(return_value=["127.0.0.1"])),
                    patch("app.javbus.acquire_upstream_request_slot", new=AsyncMock(return_value=0)),
                ):
                    response = await _request(
                        client, f"http://site.example:{port}/probe"
                    )
            await asyncio.wait_for(received.wait(), timeout=2)
        finally:
            server.close()
            await server.wait_closed()

        self.assertEqual(response.text, "ok")
        self.assertIn(b"Host: site.example:", observed["request"])

    async def test_real_https_connection_preserves_sni_for_pinned_ip(self):
        openssl = shutil.which("openssl")
        if not openssl:
            self.skipTest("OpenSSL is required to create the ephemeral test certificate")
        with tempfile.TemporaryDirectory() as temp_dir:
            cert_path = Path(temp_dir) / "cert.pem"
            key_path = Path(temp_dir) / "key.pem"
            config_path = Path(temp_dir) / "openssl.cnf"
            config_path.write_text(
                "[req]\ndistinguished_name=dn\nprompt=no\n"
                "[dn]\nCN=site.example\n"
                "[v3_ca]\nbasicConstraints=critical,CA:TRUE\n"
                "subjectAltName=DNS:site.example\n"
                "keyUsage=critical,digitalSignature,keyEncipherment,keyCertSign\n",
                encoding="ascii",
            )
            subprocess.run(
                [
                    openssl, "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                    "-keyout", str(key_path), "-out", str(cert_path), "-days", "1",
                    "-config", str(config_path), "-extensions", "v3_ca",
                    "-subj", "/CN=site.example",
                ],
                check=True,
                capture_output=True,
            )
            server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            server_context.load_cert_chain(cert_path, key_path)
            observed = {"sni": None}
            received = asyncio.Event()

            def capture_sni(_ssl_object, server_name, _context):
                observed["sni"] = server_name

            server_context.set_servername_callback(capture_sni)

            async def handle_connection(reader, writer):
                crlf = bytes((13, 10))
                observed["request"] = await reader.readuntil(crlf + crlf)
                writer.write(crlf.join([
                    b"HTTP/1.1 200 OK", b"Content-Length: 2",
                    b"Connection: close", b"", b"ok",
                ]))
                await writer.drain()
                writer.close()
                await writer.wait_closed()
                received.set()

            server = await asyncio.start_server(
                handle_connection, "127.0.0.1", 0, ssl=server_context
            )
            port = server.sockets[0].getsockname()[1]
            try:
                verify_context = ssl.create_default_context(cafile=str(cert_path))
                async with httpx.AsyncClient(
                    verify=verify_context, trust_env=False
                ) as client:
                    with (
                        patch("app.javbus._validate_target", new=AsyncMock(return_value=["127.0.0.1"])),
                        patch("app.javbus.acquire_upstream_request_slot", new=AsyncMock(return_value=0)),
                    ):
                        response = await _request(
                            client, f"https://site.example:{port}/tls-probe"
                        )
                await asyncio.wait_for(received.wait(), timeout=2)
            finally:
                server.close()
                await server.wait_closed()

        self.assertEqual(response.text, "ok")
        self.assertEqual(observed["sni"], "site.example")
        self.assertIn(b"Host: site.example:", observed["request"])

    async def test_ipv6_address_is_formatted_as_a_pinned_target(self):
        requests = []

        async def handler(request):
            requests.append(request)
            return httpx.Response(200, content=b"ok", request=request)

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler), trust_env=False
        ) as client:
            with (
                patch(
                    "app.javbus._validate_target",
                    new=AsyncMock(return_value=["2606:4700:4700::1111"]),
                ),
                patch("app.javbus.acquire_upstream_request_slot", new=AsyncMock(return_value=0)),
            ):
                await _request(client, "https://site.example/page")

        self.assertEqual(requests[0].url.host, "2606:4700:4700::1111")
        self.assertEqual(requests[0].headers["host"], "site.example")
        self.assertEqual(requests[0].extensions["sni_hostname"], "site.example")

    async def test_real_ipv6_connection_uses_pinned_address(self):
        received = asyncio.Event()
        observed = {}

        async def handle_connection(reader, writer):
            crlf = bytes((13, 10))
            observed["request"] = await reader.readuntil(crlf + crlf)
            writer.write(crlf.join([
                b"HTTP/1.1 200 OK", b"Content-Length: 2",
                b"Connection: close", b"", b"ok",
            ]))
            await writer.drain()
            writer.close()
            await writer.wait_closed()
            received.set()

        try:
            server = await asyncio.start_server(handle_connection, "::1", 0)
        except OSError as exc:
            self.skipTest(f"IPv6 loopback is unavailable: {exc}")
        port = server.sockets[0].getsockname()[1]
        try:
            async with httpx.AsyncClient(trust_env=False) as client:
                with (
                    patch("app.javbus._validate_target", new=AsyncMock(return_value=["::1"])),
                    patch("app.javbus.acquire_upstream_request_slot", new=AsyncMock(return_value=0)),
                ):
                    response = await _request(
                        client, f"http://site.example:{port}/ipv6-probe"
                    )
            await asyncio.wait_for(received.wait(), timeout=2)
        finally:
            server.close()
            await server.wait_closed()

        self.assertEqual(response.text, "ok")
        self.assertIn(b"Host: site.example:", observed["request"])

    async def test_rate_wait_does_not_hold_http_semaphore(self):
        semaphore = asyncio.Semaphore(1)
        original = javbus._fetch_semaphore
        javbus._fetch_semaphore = semaphore
        wait_started = asyncio.Event()
        allow_slot = asyncio.Event()

        async def rate_slot(_limit):
            wait_started.set()
            await allow_slot.wait()
            return 0

        async def handler(request):
            return httpx.Response(200, content=b"ok", request=request)

        try:
            async with httpx.AsyncClient(
                transport=httpx.MockTransport(handler), trust_env=False
            ) as client:
                with (
                    patch("app.javbus._validate_target", new=AsyncMock(return_value=["93.184.216.34"])),
                    patch("app.javbus.acquire_upstream_request_slot", new=rate_slot),
                ):
                    task = asyncio.create_task(_request(client, "https://site.example/page"))
                    await asyncio.wait_for(wait_started.wait(), timeout=1)
                    await asyncio.wait_for(semaphore.acquire(), timeout=0.1)
                    allow_slot.set()
                    await asyncio.sleep(0)
                    semaphore.release()
                    response = await task
            self.assertEqual(response.text, "ok")
        finally:
            javbus._fetch_semaphore = original

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
        self.assertEqual(requests[1].extensions["sni_hostname"], "cdn.example")

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
