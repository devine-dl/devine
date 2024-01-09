from typing import Union

from devine.core.drm.clearkey import ClearKey
from devine.core.drm.widevine import Widevine

DRM_T = Union[ClearKey, Widevine]


__all__ = ("ClearKey", "Widevine", "DRM_T")
