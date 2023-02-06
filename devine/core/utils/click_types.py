from __future__ import annotations

import re
from typing import Optional, Union

import click
from pywidevine.cdm import Cdm as WidevineCdm


class ContextData:
    def __init__(self, config: dict, cdm: WidevineCdm, proxy_providers: list, profile: Optional[str] = None):
        self.config = config
        self.cdm = cdm
        self.proxy_providers = proxy_providers
        self.profile = profile


class SeasonRange(click.ParamType):
    name = "ep_range"

    MIN_EPISODE = 0
    MAX_EPISODE = 999

    def parse_tokens(self, *tokens: str) -> list[str]:
        """
        Parse multiple tokens or ranged tokens as '{s}x{e}' strings.

        Supports exclusioning by putting a `-` before the token.

        Example:
            >>> sr = SeasonRange()
            >>> sr.parse_tokens("S01E01")
            ["1x1"]
            >>> sr.parse_tokens("S02E01", "S02E03-S02E05")
            ["2x1", "2x3", "2x4", "2x5"]
            >>> sr.parse_tokens("S01-S05", "-S03", "-S02E01")
            ["1x0", "1x1", ..., "2x0", (...), "2x2", (...), "4x0", ..., "5x0", ...]
        """
        if len(tokens) == 0:
            return []
        computed: list = []
        exclusions: list = []
        for token in tokens:
            exclude = token.startswith("-")
            if exclude:
                token = token[1:]
            parsed = [
                re.match(r"^S(?P<season>\d+)(E(?P<episode>\d+))?$", x, re.IGNORECASE)
                for x in re.split(r"[:-]", token)
            ]
            if len(parsed) > 2:
                self.fail(f"Invalid token, only a left and right range is acceptable: {token}")
            if len(parsed) == 1:
                parsed.append(parsed[0])
            if any(x is None for x in parsed):
                self.fail(f"Invalid token, syntax error occurred: {token}")
            from_season, from_episode = [
                int(v) if v is not None else self.MIN_EPISODE
                for k, v in parsed[0].groupdict().items() if parsed[0]  # type: ignore[union-attr]
            ]
            to_season, to_episode = [
                int(v) if v is not None else self.MAX_EPISODE
                for k, v in parsed[1].groupdict().items() if parsed[1]  # type: ignore[union-attr]
            ]
            if from_season > to_season:
                self.fail(f"Invalid range, left side season cannot be bigger than right side season: {token}")
            if from_season == to_season and from_episode > to_episode:
                self.fail(f"Invalid range, left side episode cannot be bigger than right side episode: {token}")
            for s in range(from_season, to_season + 1):
                for e in range(
                    from_episode if s == from_season else 0,
                    (self.MAX_EPISODE if s < to_season else to_episode) + 1
                ):
                    (computed if not exclude else exclusions).append(f"{s}x{e}")
        for exclusion in exclusions:
            if exclusion in computed:
                computed.remove(exclusion)
        return list(set(computed))

    def convert(
        self, value: str, param: Optional[click.Parameter] = None, ctx: Optional[click.Context] = None
    ) -> list[str]:
        return self.parse_tokens(*re.split(r"\s*[,;]\s*", value))


class LanguageRange(click.ParamType):
    name = "lang_range"

    def convert(
        self, value: Union[str, list], param: Optional[click.Parameter] = None, ctx: Optional[click.Context] = None
    ) -> list[str]:
        if isinstance(value, list):
            return value
        if not value:
            return []
        return re.split(r"\s*[,;]\s*", value)


class Quality(click.ParamType):
    name = "quality"

    def convert(self, value: str, param: Optional[click.Parameter] = None, ctx: Optional[click.Context] = None) -> int:
        try:
            return int(value.lower().rstrip("p"))
        except TypeError:
            self.fail(
                f"expected string for int() conversion, got {value!r} of type {type(value).__name__}",
                param,
                ctx
            )
        except ValueError:
            self.fail(f"{value!r} is not a valid integer", param, ctx)


SEASON_RANGE = SeasonRange()
LANGUAGE_RANGE = LanguageRange()
QUALITY = Quality()
