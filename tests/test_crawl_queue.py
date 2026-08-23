from crawler.crawl_queue import CrawlQueue


def test_add_url():
    queue = CrawlQueue()

    assert queue.add("https://example.com/about") is True
    assert queue.pending_count == 1


def test_duplicate_pending_url_is_not_added():
    queue = CrawlQueue()

    assert queue.add("https://example.com/about") is True
    assert queue.add("https://example.com/about") is False

    assert queue.pending_count == 1


def test_next_returns_url():
    queue = CrawlQueue()

    queue.add("https://example.com/about")

    assert queue.next() == "https://example.com/about"
    assert queue.pending_count == 0
    assert queue.visited_count == 1


def test_visited_url_cannot_be_added_again():
    queue = CrawlQueue()

    queue.add("https://example.com/about")

    assert queue.next() == "https://example.com/about"

    assert queue.add("https://example.com/about") is False


def test_next_empty_queue_returns_none():
    queue = CrawlQueue()

    assert queue.next() is None


def test_fifo_order():
    queue = CrawlQueue()

    queue.add("https://example.com/about")
    queue.add("https://example.com/services")
    queue.add("https://example.com/contact")

    assert queue.next() == "https://example.com/about"
    assert queue.next() == "https://example.com/services"
    assert queue.next() == "https://example.com/contact"
    assert queue.next() is None