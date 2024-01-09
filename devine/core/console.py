import logging
from datetime import datetime
from types import ModuleType
from typing import IO, Callable, Iterable, List, Literal, Mapping, Optional, Union

from rich._log_render import FormatTimeCallable, LogRender
from rich.console import Console, ConsoleRenderable, HighlighterType, RenderableType
from rich.emoji import EmojiVariant
from rich.highlighter import Highlighter, ReprHighlighter
from rich.live import Live
from rich.logging import RichHandler
from rich.padding import Padding, PaddingDimensions
from rich.status import Status
from rich.style import StyleType
from rich.table import Table
from rich.text import Text, TextType
from rich.theme import Theme

from devine.core.config import config


class ComfyLogRenderer(LogRender):
    def __call__(
        self,
        console: "Console",
        renderables: Iterable["ConsoleRenderable"],
        log_time: Optional[datetime] = None,
        time_format: Optional[Union[str, FormatTimeCallable]] = None,
        level: TextType = "",
        path: Optional[str] = None,
        line_no: Optional[int] = None,
        link_path: Optional[str] = None,
    ) -> "Table":
        from rich.containers import Renderables

        output = Table.grid(padding=(0, 5), pad_edge=True)
        output.expand = True
        if self.show_time:
            output.add_column(style="log.time")
        if self.show_level:
            output.add_column(style="log.level", width=self.level_width)
        output.add_column(ratio=1, style="log.message", overflow="fold")
        if self.show_path and path:
            output.add_column(style="log.path")
        row: List["RenderableType"] = []
        if self.show_time:
            log_time = log_time or console.get_datetime()
            time_format = time_format or self.time_format
            if callable(time_format):
                log_time_display = time_format(log_time)
            else:
                log_time_display = Text(log_time.strftime(time_format))
            if log_time_display == self._last_time and self.omit_repeated_times:
                row.append(Text(" " * len(log_time_display)))
            else:
                row.append(log_time_display)
                self._last_time = log_time_display
        if self.show_level:
            row.append(level)

        row.append(Renderables(renderables))
        if self.show_path and path:
            path_text = Text()
            path_text.append(
                path, style=f"link file://{link_path}" if link_path else ""
            )
            if line_no:
                path_text.append(":")
                path_text.append(
                    f"{line_no}",
                    style=f"link file://{link_path}#{line_no}" if link_path else "",
                )
            row.append(path_text)

        output.add_row(*row)
        return output


class ComfyRichHandler(RichHandler):
    def __init__(
        self,
        level: Union[int, str] = logging.NOTSET,
        console: Optional[Console] = None,
        *,
        show_time: bool = True,
        omit_repeated_times: bool = True,
        show_level: bool = True,
        show_path: bool = True,
        enable_link_path: bool = True,
        highlighter: Optional[Highlighter] = None,
        markup: bool = False,
        rich_tracebacks: bool = False,
        tracebacks_width: Optional[int] = None,
        tracebacks_extra_lines: int = 3,
        tracebacks_theme: Optional[str] = None,
        tracebacks_word_wrap: bool = True,
        tracebacks_show_locals: bool = False,
        tracebacks_suppress: Iterable[Union[str, ModuleType]] = (),
        locals_max_length: int = 10,
        locals_max_string: int = 80,
        log_time_format: Union[str, FormatTimeCallable] = "[%x %X]",
        keywords: Optional[List[str]] = None,
        log_renderer: Optional[LogRender] = None
    ) -> None:
        super().__init__(
            level=level,
            console=console,
            show_time=show_time,
            omit_repeated_times=omit_repeated_times,
            show_level=show_level,
            show_path=show_path,
            enable_link_path=enable_link_path,
            highlighter=highlighter,
            markup=markup,
            rich_tracebacks=rich_tracebacks,
            tracebacks_width=tracebacks_width,
            tracebacks_extra_lines=tracebacks_extra_lines,
            tracebacks_theme=tracebacks_theme,
            tracebacks_word_wrap=tracebacks_word_wrap,
            tracebacks_show_locals=tracebacks_show_locals,
            tracebacks_suppress=tracebacks_suppress,
            locals_max_length=locals_max_length,
            locals_max_string=locals_max_string,
            log_time_format=log_time_format,
            keywords=keywords,
        )
        if log_renderer:
            self._log_render = log_renderer


class ComfyConsole(Console):
    """A comfy high level console interface.

    Args:
        color_system (str, optional): The color system supported by your terminal,
            either ``"standard"``, ``"256"`` or ``"truecolor"``. Leave as ``"auto"`` to autodetect.
        force_terminal (Optional[bool], optional): Enable/disable terminal control codes, or None to auto-detect
            terminal. Defaults to None.
        force_jupyter (Optional[bool], optional): Enable/disable Jupyter rendering, or None to auto-detect Jupyter.
            Defaults to None.
        force_interactive (Optional[bool], optional): Enable/disable interactive mode, or None to auto-detect.
            Defaults to None.
        soft_wrap (Optional[bool], optional): Set soft wrap default on print method. Defaults to False.
        theme (Theme, optional): An optional style theme object, or ``None`` for default theme.
        stderr (bool, optional): Use stderr rather than stdout if ``file`` is not specified. Defaults to False.
        file (IO, optional): A file object where the console should write to. Defaults to stdout.
        quiet (bool, Optional): Boolean to suppress all output. Defaults to False.
        width (int, optional): The width of the terminal. Leave as default to auto-detect width.
        height (int, optional): The height of the terminal. Leave as default to auto-detect height.
        style (StyleType, optional): Style to apply to all output, or None for no style. Defaults to None.
        no_color (Optional[bool], optional): Enabled no color mode, or None to auto-detect. Defaults to None.
        tab_size (int, optional): Number of spaces used to replace a tab character. Defaults to 8.
        record (bool, optional): Boolean to enable recording of terminal output,
            required to call :meth:`export_html`, :meth:`export_svg`, and :meth:`export_text`. Defaults to False.
        markup (bool, optional): Boolean to enable :ref:`console_markup`. Defaults to True.
        emoji (bool, optional): Enable emoji code. Defaults to True.
        emoji_variant (str, optional): Optional emoji variant, either "text" or "emoji". Defaults to None.
        highlight (bool, optional): Enable automatic highlighting. Defaults to True.
        log_time (bool, optional): Boolean to enable logging of time by :meth:`log` methods. Defaults to True.
        log_path (bool, optional): Boolean to enable the logging of the caller by :meth:`log`. Defaults to True.
        log_time_format (Union[str, TimeFormatterCallable], optional): If ``log_time`` is enabled, either string for
            strftime or callable that formats the time. Defaults to "[%X] ".
        highlighter (HighlighterType, optional): Default highlighter.
        legacy_windows (bool, optional): Enable legacy Windows mode, or ``None`` to auto-detect. Defaults to ``None``.
        safe_box (bool, optional): Restrict box options that don't render on legacy Windows.
        get_datetime (Callable[[], datetime], optional): Callable that gets the current time as a datetime.datetime
            object (used by Console.log), or None for datetime.now.
        get_time (Callable[[], time], optional): Callable that gets the current time in seconds, default uses
            time.monotonic.
    """

    def __init__(
        self,
        *,
        color_system: Optional[
            Literal["auto", "standard", "256", "truecolor", "windows"]
        ] = "auto",
        force_terminal: Optional[bool] = None,
        force_jupyter: Optional[bool] = None,
        force_interactive: Optional[bool] = None,
        soft_wrap: bool = False,
        theme: Optional[Theme] = None,
        stderr: bool = False,
        file: Optional[IO[str]] = None,
        quiet: bool = False,
        width: Optional[int] = None,
        height: Optional[int] = None,
        style: Optional[StyleType] = None,
        no_color: Optional[bool] = None,
        tab_size: int = 8,
        record: bool = False,
        markup: bool = True,
        emoji: bool = True,
        emoji_variant: Optional[EmojiVariant] = None,
        highlight: bool = True,
        log_time: bool = True,
        log_path: bool = True,
        log_time_format: Union[str, FormatTimeCallable] = "[%X]",
        highlighter: Optional["HighlighterType"] = ReprHighlighter(),
        legacy_windows: Optional[bool] = None,
        safe_box: bool = True,
        get_datetime: Optional[Callable[[], datetime]] = None,
        get_time: Optional[Callable[[], float]] = None,
        _environ: Optional[Mapping[str, str]] = None,
        log_renderer: Optional[LogRender] = None
    ):
        super().__init__(
            color_system=color_system,
            force_terminal=force_terminal,
            force_jupyter=force_jupyter,
            force_interactive=force_interactive,
            soft_wrap=soft_wrap,
            theme=theme,
            stderr=stderr,
            file=file,
            quiet=quiet,
            width=width,
            height=height,
            style=style,
            no_color=no_color,
            tab_size=tab_size,
            record=record,
            markup=markup,
            emoji=emoji,
            emoji_variant=emoji_variant,
            highlight=highlight,
            log_time=log_time,
            log_path=log_path,
            log_time_format=log_time_format,
            highlighter=highlighter,
            legacy_windows=legacy_windows,
            safe_box=safe_box,
            get_datetime=get_datetime,
            get_time=get_time,
            _environ=_environ,
        )
        if log_renderer:
            self._log_render = log_renderer

    def status(
        self,
        status: RenderableType,
        *,
        spinner: str = "dots",
        spinner_style: str = "status.spinner",
        speed: float = 1.0,
        refresh_per_second: float = 12.5,
        pad: PaddingDimensions = (0, 5)
    ) -> Union[Live, Status]:
        """Display a comfy status and spinner.

        Args:
            status (RenderableType): A status renderable (str or Text typically).
            spinner (str, optional): Name of spinner animation (see python -m rich.spinner). Defaults to "dots".
            spinner_style (StyleType, optional): Style of spinner. Defaults to "status.spinner".
            speed (float, optional): Speed factor for spinner animation. Defaults to 1.0.
            refresh_per_second (float, optional): Number of refreshes per second. Defaults to 12.5.
            pad (Union[int, Tuple[int]]): Padding for top, right, bottom, and left borders.
                May be specified with 1, 2, or 4 integers (CSS style).

        Returns:
            Status: A Status object that may be used as a context manager.
        """
        status_renderable = super().status(
            status=status,
            spinner=spinner,
            spinner_style=spinner_style,
            speed=speed,
            refresh_per_second=refresh_per_second
        )

        if pad:
            top, right, bottom, left = Padding.unpack(pad)

            renderable_width = len(status_renderable.status)
            spinner_width = len(status_renderable.renderable.text)
            status_width = spinner_width + renderable_width

            available_width = self.width - status_width
            if available_width > right:
                # fill up the available width with padding to apply bg color
                right = available_width - right

            padding = Padding(
                status_renderable,
                (top, right, bottom, left)
            )

            return Live(
                padding,
                console=self,
                transient=True
            )

        return status_renderable


catppuccin_mocha = {
    # Colors based on "CatppuccinMocha" from Gogh themes
    "bg": "rgb(30,30,46)",
    "text": "rgb(205,214,244)",
    "text2": "rgb(162,169,193)",  # slightly darker
    "black": "rgb(69,71,90)",
    "bright_black": "rgb(88,91,112)",
    "red": "rgb(243,139,168)",
    "green": "rgb(166,227,161)",
    "yellow": "rgb(249,226,175)",
    "blue": "rgb(137,180,250)",
    "pink": "rgb(245,194,231)",
    "cyan": "rgb(148,226,213)",
    "gray": "rgb(166,173,200)",
    "bright_gray": "rgb(186,194,222)",
    "dark_gray": "rgb(54,54,84)"
}

primary_scheme = catppuccin_mocha
primary_scheme["none"] = primary_scheme["text"]
primary_scheme["grey23"] = primary_scheme["black"]
primary_scheme["magenta"] = primary_scheme["pink"]
primary_scheme["bright_red"] = primary_scheme["red"]
primary_scheme["bright_green"] = primary_scheme["green"]
primary_scheme["bright_yellow"] = primary_scheme["yellow"]
primary_scheme["bright_blue"] = primary_scheme["blue"]
primary_scheme["bright_magenta"] = primary_scheme["pink"]
primary_scheme["bright_cyan"] = primary_scheme["cyan"]
if config.set_terminal_bg:
    primary_scheme["none"] += f" on {primary_scheme['bg']}"

custom_colors = {
    "ascii.art": primary_scheme["pink"]
}
if config.set_terminal_bg:
    custom_colors["ascii.art"] += f" on {primary_scheme['bg']}"


console = ComfyConsole(
    log_time=False,
    log_path=False,
    width=80,
    theme=Theme({
        "bar.back": primary_scheme["dark_gray"],
        "bar.complete": primary_scheme["pink"],
        "bar.finished": primary_scheme["green"],
        "bar.pulse": primary_scheme["bright_black"],
        "black": primary_scheme["black"],
        "inspect.async_def": f"italic {primary_scheme['cyan']}",
        "progress.data.speed": "dark_orange",
        "repr.number": f"bold not italic {primary_scheme['cyan']}",
        "repr.number_complex": f"bold not italic {primary_scheme['cyan']}",
        "rule.line": primary_scheme["dark_gray"],
        "rule.text": primary_scheme["pink"],
        "tree.line": primary_scheme["dark_gray"],
        "status.spinner": primary_scheme["pink"],
        "progress.spinner": primary_scheme["pink"],
        **primary_scheme,
        **custom_colors
    }),
    log_renderer=ComfyLogRenderer(
        show_time=False,
        show_path=False
    )
)


__all__ = ("ComfyLogRenderer", "ComfyRichHandler", "ComfyConsole", "console")
