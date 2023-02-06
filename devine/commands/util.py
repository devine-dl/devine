import subprocess
from pathlib import Path

import click
from pymediainfo import MediaInfo

from devine.core.constants import context_settings
from devine.core.utilities import get_binary_path


@click.group(short_help="Various helper scripts and programs.", context_settings=context_settings)
def util() -> None:
    """Various helper scripts and programs."""


@util.command()
@click.argument("path", type=Path)
@click.argument("aspect", type=str)
@click.option("--letter/--pillar", default=True,
              help="Specify which direction to crop. Top and Bottom would be --letter, Sides would be --pillar.")
@click.option("-o", "--offset", type=int, default=0,
              help="Fine tune the computed crop area if not perfectly centered.")
@click.option("-p", "--preview", is_flag=True, default=False,
              help="Instantly preview the newly-set aspect crop in MPV (or ffplay if mpv is unavailable).")
def crop(path: Path, aspect: str, letter: bool, offset: int, preview: bool) -> None:
    """
    Losslessly crop H.264 and H.265 video files at the bit-stream level.
    You may provide a path to a file, or a folder of mkv and/or mp4 files.

    Note: If you notice that the values you put in are not quite working, try
    tune -o/--offset. This may be necessary on videos with sub-sampled chroma.

    Do note that you may not get an ideal lossless cropping result on some
    cases, again due to sub-sampled chroma.

    It's recommended that you try -o about 10 or so pixels and lower it until
    you get as close in as possible. Do make sure it's not over-cropping either
    as it may go from being 2px away from a perfect crop, to 20px over-cropping
    again due to sub-sampled chroma.
    """
    executable = get_binary_path("ffmpeg")
    if not executable:
        raise click.ClickException("FFmpeg executable \"ffmpeg\" not found but is required.")

    if path.is_dir():
        paths = list(path.glob("*.mkv")) + list(path.glob("*.mp4"))
    else:
        paths = [path]
    for video_path in paths:
        try:
            video_track = next(iter(MediaInfo.parse(video_path).video_tracks or []))
        except StopIteration:
            raise click.ClickException("There's no video tracks in the provided file.")

        crop_filter = {
            "HEVC": "hevc_metadata",
            "AVC": "h264_metadata"
        }.get(video_track.commercial_name)
        if not crop_filter:
            raise click.ClickException(f"{video_track.commercial_name} Codec not supported.")

        aspect_w, aspect_h = list(map(float, aspect.split(":")))
        if letter:
            crop_value = (video_track.height - (video_track.width / (aspect_w * aspect_h))) / 2
            left, top, right, bottom = map(int, [0, crop_value + offset, 0, crop_value - offset])
        else:
            crop_value = (video_track.width - (video_track.height * (aspect_w / aspect_h))) / 2
            left, top, right, bottom = map(int, [crop_value + offset, 0, crop_value - offset, 0])
        crop_filter += f"=crop_left={left}:crop_top={top}:crop_right={right}:crop_bottom={bottom}"

        if min(left, top, right, bottom) < 0:
            raise click.ClickException("Cannot crop less than 0, are you cropping in the right direction?")

        if preview:
            out_path = ["-f", "mpegts", "-"]  # pipe
        else:
            out_path = [str(video_path.with_stem(".".join(filter(bool, [
                video_path.stem,
                video_track.language,
                "crop",
                str(offset or "")
            ]))).with_suffix({
                # ffmpeg's MKV muxer does not yet support HDR
                "HEVC": ".h265",
                "AVC": ".h264"
            }.get(video_track.commercial_name, ".mp4")))]

        ffmpeg_call = subprocess.Popen([
            executable, "-y",
            "-i", str(video_path),
            "-map", "0:v:0",
            "-c", "copy",
            "-bsf:v", crop_filter
        ] + out_path, stdout=subprocess.PIPE)
        try:
            if preview:
                previewer = get_binary_path("mpv", "ffplay")
                if not previewer:
                    raise click.ClickException("MPV/FFplay executables weren't found but are required for previewing.")
                subprocess.Popen((previewer, "-"), stdin=ffmpeg_call.stdout)
        finally:
            if ffmpeg_call.stdout:
                ffmpeg_call.stdout.close()
            ffmpeg_call.wait()
