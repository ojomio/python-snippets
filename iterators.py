def partition(iterable, chunk):
    closed = False

    it = iter(iterable)
    def internal():
        nonlocal closed
        try:
            for c in range(chunk):
                yield next(it)
        except StopIteration:
            closed = True
            raise

    while not closed:
        yield internal()