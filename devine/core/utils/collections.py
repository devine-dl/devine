import itertools
from typing import Any, Iterable, Iterator, Sequence, Tuple, Type, Union


def as_lists(*args: Any) -> Iterator[Any]:
    """Converts any input objects to list objects."""
    for item in args:
        yield item if isinstance(item, list) else [item]


def as_list(*args: Any) -> list:
    """
    Convert any input objects to a single merged list object.

    Example:
        >>> as_list('foo', ['buzz', 'bizz'], 'bazz', 'bozz', ['bar'], ['bur'])
        ['foo', 'buzz', 'bizz', 'bazz', 'bozz', 'bar', 'bur']
    """
    return list(itertools.chain.from_iterable(as_lists(*args)))


def flatten(items: Any, ignore_types: Union[Type, Tuple[Type, ...]] = str) -> Iterator:
    """
    Flattens items recursively.

    Example:
    >>> list(flatten(["foo", [["bar", ["buzz", [""]], "bee"]]]))
    ['foo', 'bar', 'buzz', '', 'bee']
    >>> list(flatten("foo"))
    ['foo']
    >>> list(flatten({1}, set))
    [{1}]
    """
    if isinstance(items, (Iterable, Sequence)) and not isinstance(items, ignore_types):
        for i in items:
            yield from flatten(i, ignore_types)
    else:
        yield items


def merge_dict(source: dict, destination: dict) -> None:
    """Recursively merge Source into Destination in-place."""
    if not source:
        return
    for key, value in source.items():
        if isinstance(value, dict):
            # get node or create one
            node = destination.setdefault(key, {})
            merge_dict(value, node)
        else:
            destination[key] = value
