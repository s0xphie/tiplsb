"""TIP program enumerator.

Generates all TIP programs from a fixed command vocabulary whose compressed
payload fits in a 9x9 RGB carrier image, then runs each for inputs 0..MAX_INPUT
and records the halting ones.
"""
import zlib
import itertools
import sys
import argparse

MAGIC = b"TLSBZ1"
TRITS_PER_BYTE = 6
MAX_SLOTS = 9 * 9 * 3       # 243 pixel slots
MAX_PAYLOAD = (MAX_SLOTS - 1) // TRITS_PER_BYTE  # 40 bytes
COMPRESSED_BUDGET = MAX_PAYLOAD - len(MAGIC)      # 34 bytes
MAX_STEPS = 500
MAX_INPUT = 10

# Vocabulary: common rationals useful in TIP programs.
# Extend this list to widen the search.
DEFAULT_VOCAB = [
    "H",      # halt/zero
    "2", "3", "4", "8", "16",
    "1/2", "1/3", "1/4",
    "-1", "-2",
]


def fits(source: str) -> bool:
    compressed = zlib.compress(source.encode(), level=9)
    return len(compressed) <= COMPRESSED_BUDGET


def _mod_floor(num, den, n):
    """Compute floor((num/den) % n) as integer index (0..n-1)."""
    # floor(num/den) % n
    q = num // den  # Python floor division
    return q % n


def run_tip(commands: list, input_value=None, max_steps=MAX_STEPS):
    """Run TIP program. Returns output int or None on non-halt."""
    from fractions import Fraction
    program = [Fraction(0) if "H" in c else Fraction(c) for c in commands]
    n = len(program)
    if not n:
        return None

    ip = Fraction(1)
    iv = input_value

    last_ci = -1
    output = 0
    steps = 0

    while ip != 0:
        if steps >= max_steps:
            return None
        # Quick non-halt bail: if IP numerator/denominator too large, non-halting
        if abs(ip.numerator) > 10**30 or abs(ip.denominator) > 10**30:
            return None

        truthy = iv is not None and iv != 0
        eip = -ip if truthy else ip
        if eip < 0:
            iv -= 1

        ci = int(eip % n)
        cmd = program[ci]
        ip *= cmd
        steps += 1

        if ci == last_ci:
            output += 1
        elif ip != 0:
            output = 1
            last_ci = ci

    return output if input_value is not None else 0


def source_of(commands):
    return "\n".join(commands) + "\n"


def make_carrier_image(behaviour):
    """Generate a 9x9 RGB carrier image visualizing the behavior vector."""
    from PIL import Image, ImageDraw

    # Must stay RGB at 9x9: the encoder uses one byte-slot per channel (243 slots).
    img = Image.new("RGB", (9, 9), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    max_out = max(behaviour) or 1

    for i in range(9):
        idx = min(i, len(behaviour) - 1)
        height = int((behaviour[idx] / max_out) * 8)

        # Color derived from output value to keep the visual signature meaningful.
        hue_val = int((behaviour[idx] * 25) % 256) if max_out > 0 else 200
        r = hue_val
        g = (hue_val + 80) % 256
        b = (hue_val + 160) % 256

        for y in range(9 - height, 9):
            draw.point((i, y), fill=(r, g, b))

    return img


def main():
    import json
    import hashlib
    from pathlib import Path

    parser = argparse.ArgumentParser(
        description="Enumerate halting TIP programs that fit the 9x9 budget."
    )
    parser.add_argument("max_length", nargs="?", type=int, default=4)
    parser.add_argument(
        "--vocab",
        type=str,
        default=",".join(DEFAULT_VOCAB),
        help="Comma-separated command vocabulary, e.g. H,2,1/2,1/3",
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=0,
        help="Stop after this many unique behaviors (0 = no limit).",
    )
    parser.add_argument(
        "--max-combos",
        type=int,
        default=0,
        help="Stop after this many candidate combos checked (0 = no limit).",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=MAX_STEPS,
        help="Interpreter step cap per input/program check.",
    )
    parser.add_argument(
        "--append",
        action="store_true",
        help="Append new behaviors to existing programs/index instead of rebuilding from scratch.",
    )
    args = parser.parse_args()

    max_len = args.max_length
    vocab = [v.strip() for v in args.vocab.split(",") if v.strip()]
    if not vocab:
        raise ValueError("Vocabulary cannot be empty")

    seen = set()
    results = []

    total = sum(len(vocab) ** l for l in range(1, max_len + 1))
    checked = 0

    print(
        f"Searching lengths 1..{max_len} with {len(vocab)} commands "
        f"({total} combos max)",
        file=sys.stderr,
    )

    for length in range(1, max_len + 1):
        for combo in itertools.product(vocab, repeat=length):
            checked += 1
            if checked % 10000 == 0:
                print(f"  {checked}/{total} checked, {len(results)} found...",
                      file=sys.stderr)
            if args.max_combos and checked > args.max_combos:
                print(
                    f"Reached --max-combos={args.max_combos}, stopping early.",
                    file=sys.stderr,
                )
                break

            src = source_of(combo)
            if not fits(src):
                continue

            # Compute behaviour vector: outputs for inputs 0..MAX_INPUT
            behaviour = tuple(run_tip(list(combo), input_value=i, max_steps=args.max_steps)
                              for i in range(MAX_INPUT + 1))

            # Must halt for all inputs
            if None in behaviour:
                continue

            # Deduplicate by behaviour
            if behaviour in seen:
                continue
            seen.add(behaviour)

            results.append((src.strip(), behaviour))
            if args.max_results and len(results) >= args.max_results:
                print(
                    f"Reached --max-results={args.max_results}, stopping early.",
                    file=sys.stderr,
                )
                break
        else:
            continue
        break

    # Create output directories
    prog_dir = Path("programs")
    prog_dir.mkdir(exist_ok=True)
    enc_dir = Path("encoded_programs")
    enc_dir.mkdir(exist_ok=True)
    index_path = prog_dir / "index.json"

    index = []
    existing_ids = set()
    if args.append and index_path.exists():
        try:
            index = json.loads(index_path.read_text())
            for entry in index:
                beh = tuple(entry.get("behavior", []))
                if beh:
                    seen.add(beh)
                entry_id = entry.get("id")
                if entry_id:
                    existing_ids.add(entry_id)
            print(
                f"Loaded {len(index)} existing entries from {index_path}.",
                file=sys.stderr,
            )
        except Exception as e:
            print(f"Warning: could not load existing index: {e}", file=sys.stderr)

    print(f"\nFound {len(results)} unique halting programs in 9x9 budget.\n")
    print(f"Saving to {prog_dir}/ and {enc_dir}/ ...", file=sys.stderr)

    for i, (src, beh) in enumerate(sorted(results, key=lambda x: x[1])):
        src_id = hashlib.md5(src.encode()).hexdigest()[:8]
        beh_str = "".join(str(b) for b in beh)
        filename = f"0x{beh_str}{src_id}"
        if filename in existing_ids:
            continue
        
        # Save .tip file
        tip_path = prog_dir / f"{filename}.tip"
        tip_path.write_text(src + "\n")
        
        # Generate carrier image visualizing the behavior
        carrier_img = make_carrier_image(beh)
        carrier_tmp = prog_dir / ".carrier_tmp.png"
        carrier_img.save(carrier_tmp)
        
        # Encode into PNG
        png_encoded = False
        try:
            import subprocess
            png_path = enc_dir / f"{filename}.png"
            subprocess.run([
                sys.executable, "tiplsb.py",
                str(carrier_tmp), str(tip_path), str(png_path)
            ], capture_output=True, check=True)
            png_encoded = True
        except Exception as e:
            print(f"  Failed to encode {filename}: {e}", file=sys.stderr)
        finally:
            carrier_tmp.unlink(missing_ok=True)
        
        beh_map = " ".join(f"{j}->{v}" for j, v in enumerate(beh))
        index.append({
            "id": filename,
            "behavior": list(beh),
            "behavior_map": beh_map,
            "source": src,
            "tip_file": f"{filename}.tip",
            "png_file": f"{filename}.png" if png_encoded else None,
            "source_bytes": len(src),
            "compressed_bytes": len(zlib.compress(src.encode(), level=9))
        })
        existing_ids.add(filename)
        
        print(f"[{beh_map}]")
        print(src[:60] + ("..." if len(src) > 60 else ""))
        print()

    # Save index
    index_path.write_text(json.dumps(index, indent=2))
    print(f"\nSaved {len(index)} programs and index to {prog_dir}/", file=sys.stderr)
    print(f"Encoded images in {enc_dir}/", file=sys.stderr)


if __name__ == "__main__":
    main()
