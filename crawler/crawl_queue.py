import heapq
from itertools import count


class CrawlQueue:
    """Manage pending and visited URLs during a prioritized crawl."""

    def __init__(self) -> None:
        self._pending: list[tuple[int, int, str]] = []
        self._pending_urls: set[str] = set()
        self._visited: set[str] = set()
        self._counter = count()

    def add(self, url: str, priority: int = 0) -> bool:
        """
        Add a URL to the queue.

        Higher priority URLs are returned first.

        Returns True when the URL was added.
        Returns False when it was already queued or visited.
        """

        if url in self._visited:
            return False

        if url in self._pending_urls:
            return False

        # heapq is a min-heap, so negate priority.
        heapq.heappush(
            self._pending,
            (-priority, next(self._counter), url),
        )

        self._pending_urls.add(url)

        return True

    def next(self) -> str | None:
        """Return the highest-priority pending URL."""

        if not self._pending:
            return None

        _, _, url = heapq.heappop(self._pending)

        self._pending_urls.remove(url)
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