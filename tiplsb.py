"""TernLSB TIP interpreter/encoder.

Usage:
python tiplsb.py <imagefile>
    Decode a TIP program hidden in <imagefile> and execute it.

python tiplsb.py <input_image> <tip_source_file> <output_image>
    Encode TIP source into <input_image> and write a stego image.

Modern TIP format:
    Source files contain commands only.
    Initial instruction pointer is always 1.
"""

import sys
import select
import zlib
from fractions import Fraction
from PIL import Image

END_MARKER = 8
TRITS_PER_BYTE = 6
DEFAULT_MAX_STEPS = 1_000_000
COMPRESSED_MAGIC = b"TLSBZ1"


def _byte_to_trits(value):
    trits = [0] * TRITS_PER_BYTE
    for idx in range(TRITS_PER_BYTE - 1, -1, -1):
        trits[idx] = value % 3
        value //= 3
    return trits


def _trits_to_byte(trits):
    value = 0
    for trit in trits:
        value = value * 3 + trit
    if value > 255:
        raise ValueError("Corrupted data: trit group does not map to a byte")
    return value


def _decode_payload_bytes(raw_bytes):
    symbols = []
    for value in raw_bytes:
        symbol = value % 9
        if symbol == END_MARKER:
            break
        symbols.append(symbol)

    if len(symbols) % TRITS_PER_BYTE != 0:
        raise ValueError("Corrupted data: incomplete trit sequence")

    out = bytearray()
    for i in range(0, len(symbols), TRITS_PER_BYTE):
        group = symbols[i : i + TRITS_PER_BYTE]
        if any(trit not in (0, 1, 2) for trit in group):
            raise ValueError("Image does not contain TIP payload in this format")
        out.append(_trits_to_byte(group))

    return bytes(out)


def _decode_tip_source(raw_bytes):
    payload = _decode_payload_bytes(raw_bytes)
    if not payload.startswith(COMPRESSED_MAGIC):
        raise ValueError("Invalid or unsupported payload format")

    compressed = payload[len(COMPRESSED_MAGIC) :]
    payload = zlib.decompress(compressed)

    return payload.decode("utf-8")


def _encode_tip_source(tip_source):
    compressed = zlib.compress(tip_source.encode("utf-8"), level=9)
    payload = COMPRESSED_MAGIC + compressed
    symbols = []
    for byte in payload:
        symbols.extend(_byte_to_trits(byte))
    symbols.append(END_MARKER)
    return symbols


def _as_fraction(line):
    return Fraction(line.strip())


def _perl_truthy(value):
    if value is None:
        return False
    text = str(value)
    return text != "" and text != "0"


def _perl_decrement(value):
    text = str(value).strip()
    try:
        return int(text) - 1
    except ValueError:
        try:
            return float(text) - 1
        except ValueError:
            # Non-numeric strings become numeric 0 under arithmetic in Perl, then decrement.
            return -1


def _read_tip_input_line():
    # Avoid interactive blocking: only consume stdin when it is piped/redirected.
    if sys.stdin.isatty():
        return None
    readable, _, _ = select.select([sys.stdin], [], [], 0)
    if not readable:
        return None
    line = sys.stdin.readline()
    if line == "":
        return None
    return line


def run_tip_source(source, max_steps=DEFAULT_MAX_STEPS):
    lines = source.splitlines()
    ip = Fraction(1)
    program = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if "H" in line:
            program.append(Fraction(0))
        else:
            program.append(_as_fraction(line))

    if not program:
        raise ValueError("TIP source must include at least one instruction")

    print(f"Initial IP: {ip}", file=sys.stderr)
    program_str = " ".join(str(item) for item in program)
    print(f"Program: [{program_str}]", file=sys.stderr)

    input_line = _read_tip_input_line()
    input_defined = input_line is not None
    input_value = input_line

    last_ci = Fraction(1, 2)
    output = 0
    program_len = len(program)
    steps = 0

    while ip != 0:
        if max_steps is not None and steps >= max_steps:
            raise RuntimeError(
                f"Program did not halt within {max_steps} steps (possible infinite loop)"
            )

        eip = -ip if _perl_truthy(input_value) else ip
        if eip < 0:
            input_value = _perl_decrement(input_value)

        ci = eip % program_len
        cmd = program[int(ci)]
        print(
            f"IP {eip}: running command: {cmd} (index {ci} of program)",
            file=sys.stderr,
        )
        ip *= cmd
        steps += 1

        if ci == last_ci:
            output += 1
        elif ip != 0:
            output = 1
            last_ci = ci

    if input_defined:
        print(output)


def run(image_path):
    image = Image.open(image_path)
    tip_source = _decode_tip_source(image.tobytes())
    run_tip_source(tip_source)


def enc(input_image_path, tip_source, output_image_path):
    image = Image.open(input_image_path)
    data = list(image.tobytes())
    symbols = _encode_tip_source(tip_source)

    if len(symbols) > len(data):
        raise ValueError("Image is too small to hold TIP source")

    for i, symbol in enumerate(symbols):
        data[i] = (data[i] // 9) * 9 + symbol
        if data[i] >= 256:
            data[i] -= 9

    Image.frombytes(image.mode, image.size, bytes(data)).save(output_image_path)


if __name__ == "__main__":
    args = sys.argv[1:]

    if len(args) == 1:
        run(args[0])
    elif len(args) == 3:
        with open(args[1], "r", encoding="utf-8") as src_file:
            enc(args[0], src_file.read(), args[2])
    else:
        print("Usage:")
        print("  python tiplsb.py <imagefile>")
        print("  python tiplsb.py <input_image> <tip_source_file> <output_image>")
