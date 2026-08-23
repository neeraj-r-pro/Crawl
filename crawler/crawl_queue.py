from collections import deque


class CrawlQueue:
    """Manage pending and visited URLs during a crawl."""

    def __init__(self) -> None:
        self._pending: deque[str] = deque()
        self._visited: set[str] = set()

    def add(self, url: str) -> bool:
        """
        Add a URL to the queue.

        Returns True when the URL was added.
        Returns False when it was already queued or visited.
        """

        if url in self._visited:
            return False

        if url in self._pending:
            return False

        self._pending.append(url)

        return True

    def next(self) -> str | None:
        """Return the next pending URL and mark it as visited."""

        if not self._pending:
            return None

        url = self._pending.popleft()

        self._visited.add(url)

        return url

    @property
    def pending_count(self) -> int:
        """Return the number of URLs waiting to be crawled."""

        return len(self._pending)

    @property
    def visited_count(self) -> int:
        """Return the number of URLs already crawled."""

        return len(self._visited)

    def has_pending(self) -> bool:
        """Return True when URLs are waiting to be crawled."""

        return bool(self._pending)