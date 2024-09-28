import io
import gzip
import collections
import colorsys

import pyflate
import pyflate.huffman
from browser import document
from browser.html import BR, SPAN as S


def log_to_html(s, offset=None):
    el = S(s)
    if offset is not None:
        el.classList.add(f"message-{offset}")
        el.bind("mouseenter", el_mouseenter)
        el.bind("mouseleave", el_mouseleave)
    document["output"] <= el


def log_noop(s, offset=None):
    pass


def log(*args) -> None:
    """Log the arguments at the debug level."""
    offset = bit.tellbits()
    s = " ".join(map(str, args))
    log_messages[offset].append(s)
    log_to_html(f"[{offset}] {s}\n", offset)


def equidistributed_color(i, n):
    # https://gamedev.stackexchange.com/a/46469/22860
    return colorsys.hsv_to_rgb(
        (i * 0.618033988749895) % 1.0, 0.5, 1.0 - (i * 0.618033988749895) % 0.5
    )


def el_mouseleave(ev):
    cls = ev.target.classList[0]
    for el in document.getElementsByClassName(cls):
        el.style.backgroundColor = "white"
    document["selected_bits"].text = ""


def el_mouseenter(ev):
    cls = ev.target.classList[0]
    bits = {}
    for el in document.getElementsByClassName(cls):
        classes = el.classList
        for c in classes:
            if c.startswith("bit-"):
                class_bits = int(c[4:])
                t = class_bits
                bits[t] = el.text
        el.style.backgroundColor = "black"
    bits_s = "".join(bits[k] for k in reversed(sorted(bits.keys())))
    bits_i = int(bits_s, 2)
    document["selected_bits"].text = f"{bits_s} ({bits_i}, 0x{bits_i:02X})"
    # document['selected_bits'].text = repr(bits)


def gen_bit_to_log_message(data: bytes, log_messages) -> dict:
    log_messages_sorted = sorted(log_messages.items())
    num_log_messages = len(log_messages_sorted)
    log_message_iter = iter(log_messages_sorted)
    log_message = next(log_message_iter, None)
    log_message_s = (
        "\n".join(log_message[1]) if log_message is not None else ""
    )
    log_message_no = 0
    bit_to_log_message = {}
    for bit_number in range(0, len(data) * 8):
        # is bit_number still lower than the current log message?
        # rewind otherwise
        while log_message is not None and bit_number >= log_message[0]:
            log_message = next(log_message_iter, None)
            log_message_s = (
                "\n".join(log_message[1]) if log_message is not None else ""
            )
            log_message_no += 1
        color = equidistributed_color(log_message_no, num_log_messages)
        colors = (
            f"{int(color[0]*255)}, {int(color[1]*255)}, {int(color[2]*255)}"
        )
        style = f"color: rgb({colors});"
        cls = f"message-{log_message[0]}"
        el = S(style=style, title=log_message_s)
        el.classList.add(cls)
        el.classList.add(f"bit-{bit_number}")
        el.bind("mouseenter", el_mouseenter)
        el.bind("mouseleave", el_mouseleave)
        bit_to_log_message[bit_number] = el
    return bit_to_log_message


def print_hexdump(data: bytes) -> None:
    """Print a hexdump of the buffer."""
    hd = document["hexdump"]
    hd.clear()

    bit_to_log_message = gen_bit_to_log_message(data, log_messages)
    byte_number = 0
    for i in range(0, len(data), 4):
        b = data[i: i + 4]
        # print hex
        hd <= S(f"{i:08x}  ")
        for c in b:
            hd <= S(f"{c:02x} ")
        # align hex
        for j in range(4 - len(b)):
            hd <= S("   ")
        hd <= S(" [")
        # print binary
        for c in b:
            bits = f"{c:08b}"
            for n, bit in enumerate(bits):
                # we keep the ordering, color and log message of the bit
                # but we change the text to the actual bit
                bit_number = (byte_number * 8) + (7 - n)
                el = bit_to_log_message[bit_number]
                el.text = bit
                hd <= el
            hd <= S(" ")
            byte_number += 1
        # align binary
        for j in range(4 - len(b)):
            hd <= S("         ")
        hd <= S("] ")
        # print ASCII
        for c in b:
            # should we use a dot for non-hd <= Sable characters?
            if c < 32 or c > 126:
                hd <= S(".")
            else:
                hd <= S(chr(c))
        hd <= BR()


def run_program(*args):
    global bit, log_to_html, log_messages
    document["output"].text = ""  # Clear previous output
    s = document["input"].value
    log_to_html_copy = log_to_html
    log_messages = collections.defaultdict(list)
    try:
        buf = gzip.compress(s.encode(), mtime=0)

        # we do a dry run first to get the log messages for hexdump
        log_to_html = log_noop
        inp = io.BytesIO(buf)
        bit = pyflate.Bitfield(inp)
        _ = list(pyflate.gzip_main_bitfield(bit))

        log_to_html = log_to_html_copy
        inp = io.BytesIO(buf)
        bit = pyflate.Bitfield(inp)
        print_hexdump(buf)
        _ = list(pyflate.gzip_main_bitfield(bit))
        summary = f"Compressed {len(s)} bytes to {len(buf)} bytes."
        if len(buf) > len(s):
            summary += " Compression made it bigger by "
            summary += f"{len(buf) - len(s)} bytes."
        else:
            summary += " Compression made it smaller by "
            summary += f"{len(s) - len(buf)} bytes."
        summary += f" Compression ratio: {len(buf) / len(s):.2f}"
        document["compression_result"].text = summary
    except Exception as e:
        document["hexdump"].clear()
        log_to_html = log_to_html_copy
        log(f"Error: {e}")
        import traceback

        log(traceback.format_exc())
    finally:
        log_to_html = log_to_html_copy


log_messages = collections.defaultdict(list)
pyflate.huffman.log = log
pyflate.log = log
run_program()
document["input"].bind("input", run_program)
