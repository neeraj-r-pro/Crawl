import httpx

from crawler.http_fetcher import HTTPFetcher


def create_client(handler):
    transport = httpx.MockTransport(handler)

    return httpx.Client(
        transport=transport,
        follow_redirects=True,
    )


def test_successful_fetch():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text="<html><title>Example</title></html>",
            headers={"content-type": "text/html"},
            request=request,
        )

    client = create_client(handler)
    fetcher = HTTPFetcher(client=client)

    result = fetcher.fetch("https://example.com")

    assert result.success is True
    assert result.status_code == 200
    assert result.final_url == "https://example.com"
    assert result.content_type == "text/html"
    assert "<title>Example</title>" in result.html

    client.close()


def test_not_found_response():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            404,
            text="Not Found",
            request=request,
        )

    client = create_client(handler)
    fetcher = HTTPFetcher(client=client)

    result = fetcher.fetch("https://example.com/missing")

    assert result.success is False
    assert result.status_code == 404
    assert result.error is None

    client.close()


def test_server_error_response():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            500,
            text="Internal Server Error",
            request=request,
        )

    client = create_client(handler)
    fetcher = HTTPFetcher(client=client)

    result = fetcher.fetch("https://example.com")

    assert result.success is False
    assert result.status_code == 500

    client.close()


def test_redirect_response():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/old":
            return httpx.Response(
                301,
                headers={"location": "https://example.com/new"},
                request=request,
            )

        return httpx.Response(
            200,
            text="<html>New page</html>",
            headers={"content-type": "text/html"},
            request=request,
        )

    client = create_client(handler)
    fetcher = HTTPFetcher(client=client)

    result = fetcher.fetch("https://example.com/old")

    assert result.success is True
    assert result.status_code == 200
    assert result.final_url == "https://example.com/new"

    client.close()

def test_timeout_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout(
            "Request timed out",
            request=request,
        )

    client = create_client(handler)
    fetcher = HTTPFetcher(client=client)

    result = fetcher.fetch("https://example.com")

    assert result.success is False
    assert result.status_code is None
    assert result.html is None
    assert result.error == "Request timed out"

    client.close()

def test_connection_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(
            "Connection failed",
            request=request,
        )

    client = create_client(handler)
    fetcher = HTTPFetcher(client=client)

    result = fetcher.fetch("https://example.com")

    assert result.success is False
    assert result.status_code is None
    assert result.html is None
    assert result.error.startswith("Request failed:")

    client.close()