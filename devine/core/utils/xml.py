from typing import Union

from lxml import etree
from lxml.etree import ElementTree


def load_xml(xml: Union[str, bytes]) -> ElementTree:
    """Safely parse XML data to an ElementTree, without namespaces in tags."""
    if not isinstance(xml, bytes):
        xml = xml.encode("utf8")
    root = etree.fromstring(xml)
    for elem in root.getiterator():
        if not hasattr(elem.tag, "find"):
            # e.g. comment elements
            continue
        elem.tag = etree.QName(elem).localname
        for name, value in elem.attrib.items():
            local_name = etree.QName(name).localname
            if local_name == name:
                continue
            del elem.attrib[name]
            elem.attrib[local_name] = value
    etree.cleanup_namespaces(root)
    return root
