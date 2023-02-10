from typing import Union

from devine.core.drm.clearkey import ClearKey
from devine.core.drm.widevine import Widevine

DRM_T = Union[ClearKey, Widevine]


__ALL__ = (ClearKey, Widevine, DRM_T)
