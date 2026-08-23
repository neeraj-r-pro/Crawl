from urllib.parse import urlsplit, urlunsplit


class URLManager:
    """Utilities for validating and normalizing URLs."""

    @staticmethod
    def normalize(url: str) -> str:
        """Return a normalized representation of a URL."""
        if not isinstance(url, str) or not url.strip():
            raise ValueError("URL must be a non-empty string.")

        url = url.strip()

        parsed = urlsplit(url)

        if parsed.scheme.lower() not in {"http", "https"}:
            raise ValueError("URL must use HTTP or HTTPS.")

        if not parsed.netloc:
            raise ValueError("URL must contain a valid host.")

        scheme = parsed.scheme.lower()
        hostname = parsed.hostname.lower()

        # Preserve username/password if present.
        userinfo = ""
        if parsed.username is not None:
            userinfo = parsed.username
            if parsed.password is not None:
                userinfo += f":{parsed.password}"
            userinfo += "@"

        # Preserve non-default ports.
        port = parsed.port

        if port is not None:
            default_port = (
                (scheme == "http" and port == 80)
                or (scheme == "https" and port == 443)
            )

            if not default_port:
                hostname = f"{hostname}:{port}"

        netloc = f"{userinfo}{hostname}"

        path = parsed.path or "/"

        # Remove trailing slash except for the root path.
        if path != "/" and path.endswith("/"):
            path = path.rstrip("/")

        return urlunsplit(
            (
                scheme,
                netloc,
                path,
                parsed.query,
                "",
            )
        )

    @staticmethod
    def is_same_domain(url: str, base_url: str) -> bool:
        """Return True when two URLs belong to the same hostname."""
        url_host = urlsplit(url).hostname
        base_host = urlsplit(base_url).hostname

        if not url_host or not base_host:
            return False

        return url_host.lower() == base_host.lower()