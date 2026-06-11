#!/usr/bin/env python3
# 作用：
#   读取多通道 ADC 数据，并按 CH4_CH3_CH2_CH1 或 CH1_CH2_CH3_CH4
#   拆成 4 个通道输出。
#
# 基本用法：
#   python .\adc_128ch_reader.py data.bin -e little -f hex -n 128
#
# 说明：
#   -w, --channel-bits  每个 CH 的位宽，默认 32；例如 16 表示每个 CH 是 16bit
#   -e little/big       指整个 index 数据在 bin 文件中的字节序，默认 little
#   --channel-endian    每个 CH 内部的字节序；设置后进入“按通道分块”解析
#   --channel-order     bin 文件里 4 个 CH 的排列顺序，默认 ch4_ch3_ch2_ch1
#   -s                  把每个 CH 按有符号补码解释，默认无符号
#   --subtract          从读出的十进制结果中减去一个固定值，默认 0
#   -f             输出格式，默认 both；可选 dec/hex/both
#   -o             起始字节偏移，默认 0；支持 256 或 0x100
#   -n             最多读取多少个 index，默认读取全部
#   --csv          额外保存 CSV 文件，默认不保存

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from adc_bin_reader import read_samples, sign_extend


CHANNEL_COUNT = 4
DEFAULT_CHANNEL_BITS = 32
CHANNEL_NAMES = ("CH1", "CH2", "CH3", "CH4")
CHANNEL_ORDERS = {
    "ch4_ch3_ch2_ch1": ("CH4", "CH3", "CH2", "CH1"),
    "ch1_ch2_ch3_ch4": ("CH1", "CH2", "CH3", "CH4"),
}


def parse_channel_bits(value: str) -> int:
    try:
        channel_bits = int(value, 0)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer, such as 16 or 32") from exc

    if channel_bits <= 0:
        raise argparse.ArgumentTypeError("must be greater than 0")
    if channel_bits % 8 != 0:
        raise argparse.ArgumentTypeError("must be a multiple of 8")
    if channel_bits > 64:
        raise argparse.ArgumentTypeError("must be <= 64")
    return channel_bits


def parse_int_value(value: str) -> int:
    try:
        return int(value, 0)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer, such as 32768 or 0x8000") from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read ADC words and split them as CH4_CH3_CH2_CH1.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("bin_file", type=Path, help="Path to the .bin file")
    parser.add_argument(
        "-w",
        "--channel-bits",
        type=parse_channel_bits,
        default=DEFAULT_CHANNEL_BITS,
        help="Bit width of each channel, such as 16 or 32",
    )
    parser.add_argument(
        "-e",
        "--endian",
        choices=("little", "big"),
        default="little",
        help="Byte order used by each whole index/word in the .bin file",
    )
    parser.add_argument(
        "--channel-endian",
        choices=("little", "big"),
        default=None,
        help="Byte order inside each channel. If set, split bytes by channel first.",
    )
    parser.add_argument(
        "--channel-order",
        choices=tuple(CHANNEL_ORDERS),
        default="ch4_ch3_ch2_ch1",
        help="Channel order in the .bin file when --channel-endian is used",
    )
    parser.add_argument(
        "-s",
        "--signed",
        action="store_true",
        help="Interpret each channel as signed two's-complement",
    )
    parser.add_argument(
        "--subtract",
        type=parse_int_value,
        default=0,
        help="Subtract this value from each decoded decimal channel value",
    )
    parser.add_argument(
        "-f",
        "--format",
        choices=("dec", "hex", "both"),
        default="both",
        help="Output number format for each channel",
    )
    parser.add_argument(
        "-o",
        "--offset",
        type=lambda value: int(value, 0),
        default=0,
        help="Start byte offset, decimal or hex such as 128 or 0x80",
    )
    parser.add_argument(
        "-n",
        "--count",
        type=int,
        default=None,
        help="Maximum number of indexes to print",
    )
    parser.add_argument(
        "--csv",
        type=Path,
        default=None,
        help="Optional CSV output path",
    )
    return parser.parse_args()


def word_bytes(channel_bits: int) -> int:
    return CHANNEL_COUNT * channel_bits // 8


def channel_bytes(channel_bits: int) -> int:
    return channel_bits // 8


def decode_channel(raw_ch: int, *, channel_bits: int, signed: bool, subtract: int) -> int:
    value = sign_extend(raw_ch, channel_bits) if signed else raw_ch
    return value - subtract


def split_channels(
    raw_word: int,
    *,
    channel_bits: int,
    signed: bool,
    subtract: int,
) -> tuple[int, ...]:
    channel_mask = (1 << channel_bits) - 1
    channels: list[int] = []
    for channel_index in range(CHANNEL_COUNT):
        raw_ch = (raw_word >> (channel_index * channel_bits)) & channel_mask
        channels.append(
            decode_channel(raw_ch, channel_bits=channel_bits, signed=signed, subtract=subtract)
        )
    return tuple(channels)  # CH1, CH2, CH3, CH4


def channel_hex_values(raw_word: int, *, channel_bits: int) -> tuple[str, ...]:
    channel_mask = (1 << channel_bits) - 1
    hex_digits = channel_bits // 4
    values: list[str] = []
    for channel_index in range(CHANNEL_COUNT):
        raw_ch = (raw_word >> (channel_index * channel_bits)) & channel_mask
        values.append(f"0x{raw_ch:0{hex_digits}X}")
    return tuple(values)  # CH1, CH2, CH3, CH4


def read_channel_split_rows(
    bin_file: Path,
    *,
    channel_bits: int,
    channel_endian: str,
    channel_order: str,
    signed: bool,
    subtract: int,
    offset: int,
    count: int | None,
) -> list[tuple[int, tuple[int, ...], tuple[str, ...]]]:
    if offset < 0:
        raise ValueError("offset must be >= 0")

    data = bin_file.read_bytes()
    if offset > len(data):
        raise ValueError(f"offset {offset} is beyond file size {len(data)}")

    ch_bytes = channel_bytes(channel_bits)
    bytes_per_word = word_bytes(channel_bits)
    usable = data[offset:]
    word_count = len(usable) // bytes_per_word
    if count is not None:
        if count < 0:
            raise ValueError("count must be >= 0")
        word_count = min(word_count, count)

    trailing = len(usable) - word_count * bytes_per_word
    if trailing:
        print(
            f"warning: ignored {trailing} trailing byte(s) that do not make a full index",
            file=sys.stderr,
        )

    order = CHANNEL_ORDERS[channel_order]
    hex_digits = channel_bits // 4
    rows: list[tuple[int, tuple[int, ...], tuple[str, ...]]] = []
    for index in range(word_count):
        start = index * bytes_per_word
        word = usable[start : start + bytes_per_word]
        dec_by_name: dict[str, int] = {}
        hex_by_name: dict[str, str] = {}
        for file_pos, channel_name in enumerate(order):
            ch_start = file_pos * ch_bytes
            raw_bytes = word[ch_start : ch_start + ch_bytes]
            raw_ch = int.from_bytes(raw_bytes, byteorder=channel_endian, signed=False)
            dec_by_name[channel_name] = decode_channel(
                raw_ch, channel_bits=channel_bits, signed=signed, subtract=subtract
            )
            hex_by_name[channel_name] = f"0x{raw_ch:0{hex_digits}X}"

        rows.append(
            (
                index,
                tuple(dec_by_name[name] for name in CHANNEL_NAMES),
                tuple(hex_by_name[name] for name in CHANNEL_NAMES),
            )
        )
    return rows


def print_rows(
    rows: list[tuple[int, tuple[int, ...], tuple[str, ...]]],
    *,
    output_format: str,
) -> None:
    if output_format == "dec":
        print("index," + ",".join(CHANNEL_NAMES))
        for index, dec_values, _hex_values in rows:
            print(f"{index}," + ",".join(str(value) for value in dec_values))
    elif output_format == "hex":
        print("index," + ",".join(CHANNEL_NAMES))
        for index, _dec_values, hex_values in rows:
            print(f"{index}," + ",".join(hex_values))
    else:
        headers = []
        for name in CHANNEL_NAMES:
            headers.extend((f"{name}_dec", f"{name}_hex"))
        print("index," + ",".join(headers))
        for index, dec_values, hex_values in rows:
            cells: list[str] = []
            for dec_value, hex_value in zip(dec_values, hex_values):
                cells.extend((str(dec_value), hex_value))
            print(f"{index}," + ",".join(cells))


def write_csv(
    csv_file: Path,
    rows: list[tuple[int, tuple[int, ...], tuple[str, ...]]],
    *,
    output_format: str,
) -> None:
    with csv_file.open("w", newline="", encoding="utf-8") as output:
        writer = csv.writer(output)
        if output_format == "dec":
            writer.writerow(["index", *CHANNEL_NAMES])
            for index, dec_values, _hex_values in rows:
                writer.writerow([index, *dec_values])
        elif output_format == "hex":
            writer.writerow(["index", *CHANNEL_NAMES])
            for index, _dec_values, hex_values in rows:
                writer.writerow([index, *hex_values])
        else:
            headers = []
            for name in CHANNEL_NAMES:
                headers.extend((f"{name}_dec", f"{name}_hex"))
            writer.writerow(["index", *headers])
            for index, dec_values, hex_values in rows:
                cells: list[int | str] = []
                for dec_value, hex_value in zip(dec_values, hex_values):
                    cells.extend((dec_value, hex_value))
                writer.writerow([index, *cells])


def main() -> int:
    args = parse_args()
    bytes_per_word = word_bytes(args.channel_bits)
    try:
        if args.channel_endian is None:
            words = read_samples(
                args.bin_file,
                bytes_per_sample=bytes_per_word,
                endian=args.endian,
                signed=False,
                offset=args.offset,
                count=args.count,
            )
            rows = []
            for index, raw_word, _value in words:
                rows.append(
                    (
                        index,
                        split_channels(
                            raw_word,
                            channel_bits=args.channel_bits,
                            signed=args.signed,
                            subtract=args.subtract,
                        ),
                        channel_hex_values(raw_word, channel_bits=args.channel_bits),
                    )
                )
        else:
            rows = read_channel_split_rows(
                args.bin_file,
                channel_bits=args.channel_bits,
                channel_endian=args.channel_endian,
                channel_order=args.channel_order,
                signed=args.signed,
                subtract=args.subtract,
                offset=args.offset,
                count=args.count,
            )
    except OSError as exc:
        print(f"error: cannot read {args.bin_file}: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print_rows(rows, output_format=args.format)
    if args.csv is not None:
        write_csv(args.csv, rows, output_format=args.format)
        print(f"saved CSV: {args.csv}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
