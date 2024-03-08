from typing import Optional, Union


class SearchResult:
    def __init__(
        self,
        id_: Union[str, int],
        title: str,
        description: Optional[str] = None,
        label: Optional[str] = None,
        url: Optional[str] = None
    ):
        """
        A Search Result for any support Title Type.

        Parameters:
            id_: The search result's Title ID.
            title: The primary display text, e.g., the Title's Name.
            description: The secondary display text, e.g., the Title's Description or
                further title information.
            label: The tertiary display text. This will typically be used to display
                an informative label or tag to the result. E.g., "unavailable", the
                title's price tag, region, etc.
            url: A hyperlink to the search result or title's page.
        """
        if not isinstance(id_, (str, int)):
            raise TypeError(f"Expected id_ to be a {str} or {int}, not {type(id_)}")
        if not isinstance(title, str):
            raise TypeError(f"Expected title to be a {str}, not {type(title)}")
        if not isinstance(description, (str, type(None))):
            raise TypeError(f"Expected description to be a {str}, not {type(description)}")
        if not isinstance(label, (str, type(None))):
            raise TypeError(f"Expected label to be a {str}, not {type(label)}")
        if not isinstance(url, (str, type(None))):
            raise TypeError(f"Expected url to be a {str}, not {type(url)}")

        self.id = id_
        self.title = title
        self.description = description
        self.label = label
        self.url = url


__all__ = ("SearchResult",)
