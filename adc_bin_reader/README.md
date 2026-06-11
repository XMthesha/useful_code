# ADC Bin Reader

`adc_bin_reader.py` is a small Python command-line utility for viewing ADC data
stored in a `.bin` file. It prints each fixed-width index/sample as decimal,
hex, or both.

## Basic Usage

From VS Code Terminal or PowerShell:

```powershell
python .\adc_bin_reader.py path\to\data.bin
```

If Windows only has the Python Launcher available, use `py` instead:

```powershell
py .\adc_bin_reader.py path\to\data.bin
```

Default assumptions:

- 2 bytes per index/sample
- little-endian byte order
- unsigned values
- output includes both decimal and hex

## Common Examples

Read the first 32 unsigned 16-bit samples:

```powershell
python .\adc_bin_reader.py data.bin -b 2 -n 32
```

Read the first 128 indexes, with each index containing 16 bytes / 128 bits:

```powershell
python .\adc_bin_reader.py data.bin -b 16 -f hex -n 128
```

Split 128-bit words into four 32-bit channels when
`[127:0] = CH4_CH3_CH2_CH1`:

```powershell
python .\adc_128ch_reader.py data.bin -e little -f hex -n 128
```

If the 128-bit word is printed as `0xCH4CH3CH2CH1`, the channel reader outputs
columns in this order: `CH1,CH2,CH3,CH4`.

For another data format where each channel is 16 bits, use `-w 16`. The script
then reads 8 bytes per index:

```powershell
python .\adc_128ch_reader.py data.bin -w 16 -e little -f hex -n 128
```

If the file stores channels as `CH4_CH3_CH2_CH1`, and each 16-bit channel itself
is little-endian, use channel-level endian parsing:

```powershell
python .\adc_128ch_reader.py data.bin -w 16 --channel-order ch4_ch3_ch2_ch1 --channel-endian little -s -f both -n 128
```

Read signed 16-bit samples:

```powershell
python .\adc_bin_reader.py data.bin -b 2 --signed
```

Read 24-bit ADC samples, big-endian, and show both decimal and hex:

```powershell
python .\adc_bin_reader.py data.bin -b 3 -e big --signed -f both
```

Start from byte offset `0x100` and print 20 samples:

```powershell
python .\adc_bin_reader.py data.bin -o 0x100 -n 20
```

Export the decoded values to CSV:

```powershell
python .\adc_bin_reader.py data.bin -b 3 -e big --signed --csv decoded.csv
```

## Output

Example:

```text
index,dec,hex
0,123,0x007B
1,-8,0xFFF8
2,2048,0x0800
```

`hex` is always the raw ADC sample value before signed conversion. `dec` is the
interpreted value, so it changes when `--signed` is used.

## Options

- `-b`, `--bytes-per-sample`: bytes in one output index/sample. Default is `2`.
  Use `-b 16` for 128-bit data.
- `-n`, `--count`: number of indexes/samples to print, not number of bytes.
- `adc_128ch_reader.py -w`, `--channel-bits`: bit width of each channel.
  Default is `32`; use `-w 16` for 16-bit CH1~CH4 data.
- `adc_128ch_reader.py --channel-endian`: byte order inside each CH. Use this
  when the file is stored channel by channel, for example each 16-bit CH is
  little-endian.
- `adc_128ch_reader.py --channel-order`: channel order in the file when using
  `--channel-endian`. Default is `ch4_ch3_ch2_ch1`.
