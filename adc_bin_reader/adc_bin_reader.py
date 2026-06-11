#!/usr/bin/env python3
# 作用：
#   读取 ADC 采集保存的 .bin 文件，把固定字节宽度的数据按十进制、
#   十六进制或二者同时打印出来，方便在 VS Code 终端/命令行中快速查看。
#
# 基本用法：
#   python .\adc_bin_reader.py data.bin -b 2 -n 32
#
# 配置项：
#   bin_file                  要读取的 .bin 文件路径，必填
#   -b, --bytes-per-sample    每个 index/采样点占几个字节，默认 2；如 16 表示 128bit
#   -e, --endian              字节序，默认 little；可选 little/big
#   -s, --signed              按有符号补码解释数据，默认无符号
#   -f, --format              输出格式，默认 both；可选 dec/hex/both
#   -o, --offset              从第几个字节开始读，默认 0；支持 256 或 0x100
#   -n, --count               最多读取多少个采样点，默认读取全部
#   --csv                     额外保存 CSV 文件，默认不保存
"""
Read ADC samples from a .bin file and print them as decimal and/or hex.

This is intentionally a small command-line utility for lab/debug use. It assumes
the bin file is a stream of fixed-width ADC samples such as 16-bit or 24-bit
values.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path


MIN_BYTES_PER_SAMPLE = 1
MAX_BYTES_PER_SAMPLE = 64


def parse_bytes_per_sample(value: str) -> int:
    try:
        bytes_per_sample = int(value, 0)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer, such as 4 or 0x10") from exc

    if not MIN_BYTES_PER_SAMPLE <= bytes_per_sample <= MAX_BYTES_PER_SAMPLE:
        raise argparse.ArgumentTypeError(
            f"must be between {MIN_BYTES_PER_SAMPLE} and {MAX_BYTES_PER_SAMPLE}"
        )
    return bytes_per_sample


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read fixed-width ADC data from a .bin file.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("bin_file", type=Path, help="Path to the .bin file")
    parser.add_argument(
        "-b",
        "--bytes-per-sample",
        type=parse_bytes_per_sample,
        default=2,
        help="Number of bytes in one index/sample, such as 4 for 32-bit or 16 for 128-bit",
    )
    parser.add_argument(
        "-e",
        "--endian",
        choices=("little", "big"),
        default="little",
        help="Byte order used in the .bin file",
    )
    parser.add_argument(
        "-s",
        "--signed",
        action="store_true",
        help="Interpret samples as signed two's-complement values",
    )
    parser.add_argument(
        "-f",
        "--format",
        choices=("dec", "hex", "both"),
        default="both",
        help="Output number format",
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
        help="Maximum number of samples to print",
    )
    parser.add_argument(
        "--csv",
        type=Path,
        default=None,
        help="Optional CSV output path",
    )
    return parser.parse_args()


def sign_extend(value: int, bits: int) -> int:
    sign_bit = 1 << (bits - 1)
    return (value ^ sign_bit) - sign_bit


def read_samples(
    bin_file: Path,
    *,
    bytes_per_sample: int,
    endian: str,
    signed: bool,
    offset: int,
    count: int | None,
) -> list[tuple[int, int, int]]:
    if offset < 0:
        raise ValueError("offset must be >= 0")

    data = bin_file.read_bytes()
    if offset > len(data):
        raise ValueError(f"offset {offset} is beyond file size {len(data)}")

    usable = data[offset:]
    sample_count = len(usable) // bytes_per_sample
    if count is not None:
        if count < 0:
            raise ValueError("count must be >= 0")
        sample_count = min(sample_count, count)

    trailing = len(usable) - sample_count * bytes_per_sample
    if trailing:
        print(
            f"warning: ignored {trailing} trailing byte(s) that do not make a full sample",
            file=sys.stderr,
        )

    bits = bytes_per_sample * 8
    rows: list[tuple[int, int, int]] = []
    for index in range(sample_count):
        start = index * bytes_per_sample
        raw_bytes = usable[start : start + bytes_per_sample]
        raw = int.from_bytes(raw_bytes, byteorder=endian, signed=False)
        value = sign_extend(raw, bits) if signed else raw
        rows.append((index, raw, value))
    return rows


def hex_width(bytes_per_sample: int) -> int:
    return bytes_per_sample * 2


def print_rows(
    rows: list[tuple[int, int, int]],
    *,
    output_format: str,
    bytes_per_sample: int,
) -> None:
    width = hex_width(bytes_per_sample)
    if output_format == "dec":
        print("index,dec")
        for index, _raw, value in rows:
            print(f"{index},{value}")
    elif output_format == "hex":
        print("index,hex")
        for index, raw, _value in rows:
            print(f"{index},0x{raw:0{width}X}")
    else:
        print("index,dec,hex")
        for index, raw, value in rows:
            print(f"{index},{value},0x{raw:0{width}X}")


def write_csv(
    csv_file: Path,
    rows: list[tuple[int, int, int]],
    *,
    bytes_per_sample: int,
) -> None:
    width = hex_width(bytes_per_sample)
    with csv_file.open("w", newline="", encoding="utf-8") as output:
        writer = csv.writer(output)
        writer.writerow(["index", "dec", "hex"])
        for index, raw, value in rows:
            writer.writerow([index, value, f"0x{raw:0{width}X}"])


def main() -> int:
    args = parse_args()
    try:
        rows = read_samples(
            args.bin_file,
            bytes_per_sample=args.bytes_per_sample,
            endian=args.endian,
            signed=args.signed,
            offset=args.offset,
            count=args.count,
        )
    except OSError as exc:
        print(f"error: cannot read {args.bin_file}: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print_rows(rows, output_format=args.format, bytes_per_sample=args.bytes_per_sample)
    if args.csv is not None:
        write_csv(args.csv, rows, bytes_per_sample=args.bytes_per_sample)
        print(f"saved CSV: {args.csv}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
