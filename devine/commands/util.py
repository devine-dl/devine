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
            out_path = [str(video_path.with_name(".".join(filter(bool, [
                video_path.stem,
                video_track.language,
                "crop",
                str(offset or ""),
                {
                    # ffmpeg's MKV muxer does not yet support HDR
                    "HEVC": "h265",
                    "AVC": "h264"
                }.get(video_track.commercial_name, ".mp4")
            ]))))]

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


@util.command(name="range")
@click.argument("path", type=Path)
@click.option("--full/--limited", is_flag=True,
              help="Full: 0..255, Limited: 16..235 (16..240 YUV luma)")
@click.option("-p", "--preview", is_flag=True, default=False,
              help="Instantly preview the newly-set video range in MPV (or ffplay if mpv is unavailable).")
def range_(path: Path, full: bool, preview: bool) -> None:
    """
    Losslessly set the Video Range flag to full or limited at the bit-stream level.
    You may provide a path to a file, or a folder of mkv and/or mp4 files.

    If you ever notice blacks not being quite black, and whites not being quite white,
    then you're video may have the range set to the wrong value. Flip its range to the
    opposite value and see if that fixes it.
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

        metadata_key = {
            "HEVC": "hevc_metadata",
            "AVC": "h264_metadata"
        }.get(video_track.commercial_name)
        if not metadata_key:
            raise click.ClickException(f"{video_track.commercial_name} Codec not supported.")

        if preview:
            out_path = ["-f", "mpegts", "-"]  # pipe
        else:
            out_path = [str(video_path.with_name(".".join(filter(bool, [
                video_path.stem,
                video_track.language,
                "range",
                ["limited", "full"][full],
                {
                    # ffmpeg's MKV muxer does not yet support HDR
                    "HEVC": "h265",
                    "AVC": "h264"
                }.get(video_track.commercial_name, ".mp4")
            ]))))]

        ffmpeg_call = subprocess.Popen([
            executable, "-y",
            "-i", str(video_path),
            "-map", "0:v:0",
            "-c", "copy",
            "-bsf:v", f"{metadata_key}=video_full_range_flag={int(full)}"
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


@util.command()
@click.argument("path", type=Path)
@click.option("-m", "--map", "map_", type=str, default="0",
              help="Test specific streams by setting FFmpeg's -map parameter.")
def test(path: Path, map_: str) -> None:
    """
    Decode an entire video and check for any corruptions or errors using FFmpeg.
    You may provide a path to a file, or a folder of mkv and/or mp4 files.

    Tests all streams within the file by default. Subtitles cannot be tested.
    You may choose specific streams using the -m/--map parameter. E.g.,
    '0:v:0' to test the first video stream, or '0:a' to test all audio streams.
    """
    executable = get_binary_path("ffmpeg")
    if not executable:
        raise click.ClickException("FFmpeg executable \"ffmpeg\" not found but is required.")

    if path.is_dir():
        paths = list(path.glob("*.mkv")) + list(path.glob("*.mp4"))
    else:
        paths = [path]
    for video_path in paths:
        print("Starting...")
        p = subprocess.Popen([
            executable, "-hide_banner",
            "-benchmark",
            "-i", str(video_path),
            "-map", map_,
            "-sn",
            "-f", "null",
            "-"
        ], stderr=subprocess.PIPE, universal_newlines=True)
        reached_output = False
        errors = 0
        for line in p.stderr:
            line = line.strip()
            if "speed=" in line:
                reached_output = True
            if not reached_output:
                continue
            if line.startswith("["):  # error of some kind
                errors += 1
                stream, error = line.split("] ", maxsplit=1)
                stream = stream.split(" @ ")[0]
                line = f"{stream} ERROR: {error}"
            print(line)
        p.stderr.close()
        print(f"Finished with {errors} Errors, Cleaning up...")
        p.terminate()
        p.wait()
