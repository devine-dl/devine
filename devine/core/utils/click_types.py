import re
from typing import Any, Optional, Union

import click
from click.shell_completion import CompletionItem
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


class QualityList(click.ParamType):
    name = "quality_list"

    def convert(
        self,
        value: Union[str, list[str]],
        param: Optional[click.Parameter] = None,
        ctx: Optional[click.Context] = None
    ) -> list[int]:
        if not value:
            return []
        if not isinstance(value, list):
            value = value.split(",")
        resolutions = []
        for resolution in value:
            try:
                resolutions.append(int(resolution.lower().rstrip("p")))
            except TypeError:
                self.fail(
                    f"Expected string for int() conversion, got {resolution!r} of type {type(resolution).__name__}",
                    param,
                    ctx
                )
            except ValueError:
                self.fail(f"{resolution!r} is not a valid integer", param, ctx)
        return sorted(resolutions, reverse=True)


class MultipleChoice(click.Choice):
    """
    The multiple choice type allows multiple values to be checked against
    a fixed set of supported values.

    It internally uses and is based off of click.Choice.
    """

    name = "multiple_choice"

    def __repr__(self) -> str:
        return f"MultipleChoice({list(self.choices)})"

    def convert(
        self,
        value: Any,
        param: Optional[click.Parameter] = None,
        ctx: Optional[click.Context] = None
    ) -> list[Any]:
        if not value:
            return []
        if isinstance(value, str):
            values = value.split(",")
        elif isinstance(value, list):
            values = value
        else:
            self.fail(
                f"{value!r} is not a supported value.",
                param,
                ctx
            )

        chosen_values: list[Any] = []
        for value in values:
            chosen_values.append(super().convert(value, param, ctx))

        return chosen_values

    def shell_complete(
        self,
        ctx: click.Context,
        param: click.Parameter,
        incomplete: str
    ) -> list[CompletionItem]:
        """
        Complete choices that start with the incomplete value.

        Parameters:
            ctx: Invocation context for this command.
            param: The parameter that is requesting completion.
            incomplete: Value being completed. May be empty.
        """
        incomplete = incomplete.rsplit(",")[-1]
        return super(self).shell_complete(ctx, param, incomplete)


SEASON_RANGE = SeasonRange()
LANGUAGE_RANGE = LanguageRange()
QUALITY_LIST = QualityList()
