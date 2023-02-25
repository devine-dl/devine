from rich.console import Console
from rich.theme import Theme


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

custom_colors = {
    "ascii.art": primary_scheme["pink"]
}


console = Console(
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
    })
)


__ALL__ = (console,)
