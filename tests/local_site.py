"""
A tiny in-process HTTP server that serves a fake "company website" with
deliberately varied, broken, and edge-case pages -- so the fetcher and
crawler can be tested end-to-end without needing real internet access
(the sandbox this was built in does not allow arbitrary outbound
network calls, so this is also how the crawler's error handling is
proven, not just its happy path).

Routes:
  /                 -> normal homepage with nav links
  /about             -> normal about page (address, phone)
  /products          -> normal products page, also links to 8 parameterized
                         category-filter variants (?categories=N) to test
                         path-variant-aware queue prioritization
  /products?categories=N -> N in 1..8, thin "category filter" pages
  /services          -> normal services page
  /contact           -> normal contact page
  /slow              -> sleeps 2s before responding (timeout test target)
  /error500          -> HTTP 500 (should be retried, then recorded as failed)
  /error404          -> HTTP 404
  /error403          -> HTTP 403
  /redirect-me       -> 302 redirect to /about
  /redirect-to-spa    -> 302 redirect to /spa (redirect + dynamic-render combo)
  /empty             -> 200 OK but empty body
  /binary.pdf        -> served with a PDF content-type (should be rejected as non-HTML)
  /spa                -> near-empty shell (SPA detection target)
  /malformed          -> intentionally broken/unclosed HTML tags
  /huge               -> body larger than the configured size cap
  /robots.txt          -> disallows /disallowed
  /disallowed          -> should never be fetched if robots.txt is honoured
  /business/other-company-example -> a third-party business listing page
                         (different company name, own contact/address) --
                         should be crawled but excluded from aggregation
"""
from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PRODUCTS_NAV = "".join(
    f'<a href="/products?categories={i}">Category {i}</a>' for i in range(1, 9)
)

PAGES = {
    "/": """
        <html><head><title>TestCo | Home</title>
        <meta property="og:site_name" content="TestCo Solutions">
        <meta name="description" content="TestCo builds reliable widgets for manufacturing."></head>
        <body><h1>TestCo Solutions</h1>
        <nav>
          <a href="/about">About</a>
          <a href="/products">Products</a>
          <a href="/services">Services</a>
          <a href="/contact">Contact</a>
          <a href="/error500">Broken link</a>
          <a href="/error404">Missing link</a>
          <a href="/redirect-me">Redirecting link</a>
          <a href="/redirect-to-spa">Redirecting to app</a>
          <a href="/spa">App</a>
          <a href="/binary.pdf">Brochure</a>
          <a href="/disallowed">Disallowed</a>
          <a href="/business/other-company-example">Other Company Example</a>
        </nav>
        </body></html>
    """,
    "/about": """
        <html><head><title>About | TestCo</title>
        <meta name="description" content="TestCo is headquartered in Bengaluru, India."></head>
        <body><h1>About TestCo</h1>
        <address>TestCo Solutions, 4th Block, Koramangala, Bengaluru 560034, India</address>
        <p>Call +91 80 1234 5678 or email hello@testco.example</p>
        </body></html>
    """,
    "/products": f"""
        <html><head><title>Products | TestCo</title></head>
        <body><h1>Products</h1>
        <h2>Widget A</h2><h2>Widget B</h2>
        <nav class="category-filters">{PRODUCTS_NAV}</nav>
        </body></html>
    """,
    "/services": """
        <html><head><title>Services | TestCo</title></head>
        <body><h1>Services</h1>
        <h2>Installation</h2><h2>Maintenance</h2>
        </body></html>
    """,
    "/contact": """
        <html><head><title>Contact | TestCo</title></head>
        <body><h1>Contact Us</h1>
        <address>TestCo Regional Office, MG Road, Pune, India</address>
        <p>Email: support@testco.example</p>
        </body></html>
    """,
    "/empty": "",
    "/spa": (
        '<html><head><title>Loading</title></head><body>'
        '<div id="root">Loading...</div>'
        '<script>'
        'fetch("/spa-data").then(function(r){return r.text();})'
        '.then(function(html){document.getElementById("root").innerHTML = html;});'
        '</script>'
        '</body></html>'
    ),
    "/spa-data": (
        '<h1>Acme JS Corp</h1>'
        '<p>This real company content is fetched from a separate endpoint by '
        'client-side JavaScript after the initial page load (the common '
        'pattern for API-driven SPAs) and is NOT present anywhere in the '
        'static HTML response for /spa -- only a headless browser that '
        'executes JavaScript and waits for the fetch can see it. '
        'Contact: hello@acmejscorp.example</p>'
    ),
    "/malformed": "<html><body><h1>Broken<div><p>Unclosed tags here",
    "/business/other-company-example": """
        <html><head><title>Other Company Example Pvt Ltd</title>
        <meta property="og:site_name" content="Other Company Example Pvt Ltd">
        <meta name="description" content="Other Company Example is a totally different business listed on TestCo."></head>
        <body><h1>Other Company Example Pvt Ltd</h1>
        <address>Other Company Example, 99 Elsewhere Road, Chennai, India</address>
        <p>Email: contact@othercompanyexample.example</p>
        <p>Call +91 44 9999 8888</p>
        </body></html>
    """,
}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass  # silence test server logging

    def do_GET(self):
        path = self.path.split("?")[0]

        if path == "/robots.txt":
            self._send(200, "text/plain", "User-agent: *\nDisallow: /disallowed\n")
        elif path == "/slow":
            import time
            time.sleep(2)
            self._send(200, "text/html", "<html><body>slow page</body></html>")
        elif path == "/error500":
            self._send(500, "text/html", "<html><body>server error</body></html>")
        elif path == "/error404":
            self._send(404, "text/html", "<html><body>not found</body></html>")
        elif path == "/error403":
            self._send(403, "text/html", "<html><body>forbidden</body></html>")
        elif path == "/redirect-me":
            self.send_response(302)
            self.send_header("Location", "/about")
            self.send_header("Content-Length", "0")
            self.end_headers()
        elif path == "/redirect-to-spa":
            self.send_response(302)
            self.send_header("Location", "/spa")
            self.send_header("Content-Length", "0")
            self.end_headers()
        elif path == "/binary.pdf":
            self._send(200, "application/pdf", "%PDF-1.4 fake pdf bytes")
        elif path == "/huge":
            self._send(200, "text/html", "<html><body>" + ("x" * (6_000_000)) + "</body></html>")
        elif path == "/disallowed":
            self._send(200, "text/html", "<html><body>should not be fetched</body></html>")
        elif path == "/products" and self.path != "/products":
            # a parameterized /products?categories=N variant
            n = self.path.split("=")[-1]
            self._send(200, "text/html", f"<html><head><title>Category {n}</title></head><body><h1>Category {n}</h1></body></html>")
        elif path in PAGES:
            self._send(200, "text/html", PAGES[path])
        else:
            self._send(404, "text/html", "<html><body>not found</body></html>")

    def _send(self, status, content_type, body):
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


class LocalSite:
    """Context manager that runs the fake site on 127.0.0.1:<free port>."""

    def __init__(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        self.base_url = f"http://127.0.0.1:{self.port}"
        self._thread = None

    def __enter__(self):
        self._thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()
