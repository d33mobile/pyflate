import io
import gzip
import collections
import colorsys
import traceback

import pyflate
import pyflate.huffman

try:
    from browser import document
    import browser.html as H
    from browser.html import BR, SPAN as S

    BROWSER = True
except ImportError:
    import sys

    sys.exit("ERROR: This script is meant to be run in a browser.")
    BROWSER = False  # pylint: disable=unreachable


# Expressions like "document <= BR()" result in "is assigned to nothing"
# warning. Let's ignore it:
#
# pylint: disable=expression-not-assigned,pointless-statement

# We need a few globals, let's initialize them to None explicitly.
# log_to_html is a function that logs a message to the output area and will
# be monkey-patched to log_noop during the dry run.
#
# pylint: disable=function-redefined
bit = log_to_html = None
log_messages = collections.defaultdict(list)


def log_to_html(s, offset=None):
    """Log the string to the output area. Bind mouseenter and mouseleave
    events to the element so that we can highlight the corresponding bits
    in the hexdump and message log."""
    el = S(s)
    if offset is not None:
        el.classList.add(f"message-{offset}")
        el.classList.add(f"log-message-{offset}")
        el.bind("mouseenter", el_mouseenter)
        el.bind("mouseleave", el_mouseleave)
    document["output"] <= el


def log_noop(_, __=None):
    """No-op log function used during the dry run."""
    pass


def log(*args) -> None:
    """Log the arguments at the debug level."""
    offset = bit.tellbits()
    s = " ".join(map(str, args))
    log_messages[offset].append(s)
    log_to_html(f"[{offset}] {s}\n", offset)


def equidistributed_color(i):
    """Generate an equidistributed color, so that the bit colors are
    visually distinct."""
    # https://gamedev.stackexchange.com/a/46469/22860
    return colorsys.hsv_to_rgb(
        (i * 0.618033988749895) % 1.0, 0.6, 0.85 + (i * 0.618033988749895) % 0.15
    )


def el_mouseleave(ev):
    """Handle mouseleave event by undoing the highlighting."""
    cls = ev.target.classList[0]
    for el in document.getElementsByClassName(cls):
        el.style.backgroundColor = ""
    document["selected_bits"].text = "\u2014"


def el_mouseenter(ev):
    """Handle mouseenter event by highlighting the corresponding bits in
    the hexdump and message log."""

    cls = ev.target.classList[0]
    bits = {}
    for el in document.getElementsByClassName(cls):
        classes = el.classList
        for c in classes:
            if c.startswith("bit-"):
                class_bits = int(c[4:])
                t = class_bits
                bits[t] = el.text
        el.style.backgroundColor = "rgba(108, 140, 255, 0.3)"
    bits_s = "".join(bits[k] for k in reversed(sorted(bits.keys())))
    bits_i = int(bits_s, 2)
    document["selected_bits"].text = f"{bits_s} ({bits_i}, 0x{bits_i:02X})"

    # for all elements with class huffman-{bits_i}, scroll them into view
    for el in document.getElementsByClassName(f"huffman-{bits_i}"):
        el.scrollIntoView()

    # figure out if the bit is a bit or a log message.
    # we need to scroll the OPPOSITE type of element into view
    initiating_element = ev.target
    is_bit = False
    for class_name in initiating_element.classList:
        if class_name.startswith("bit-"):
            is_bit = True
            break

    # find element in log and scroll to it.
    num = cls.split("-")[-1]
    for el in document.getElementsByClassName(f"message-{num}"):

        # is the element a bit or a log message?
        el_is_bit = False
        for class_name in el.classList:
            if class_name.startswith("bit-"):
                el_is_bit = True
                break

        # scroll the opposite type of element into view
        if el_is_bit != is_bit:
            el.scrollIntoView()
            break


def gen_bit_to_log_message(data: bytes, log_messages) -> dict:
    """Generate a mapping from bit number to log message DOM element that
    has colors and log messages tied to it."""

    log_message_iter = iter(sorted(log_messages.items()))
    log_message_no = -1

    def next_log_message(log_message_iter):
        nonlocal log_message_no
        log_message = next(log_message_iter, None)
        log_message_s = (
            "\n".join(log_message[1]) if log_message is not None else ""
        )
        log_message_bitno = log_message[0]
        log_message_no += 1
        color = equidistributed_color(log_message_no)
        colors = ",".join(f"{int(c*255)}" for c in color)
        style = f"color: rgb({colors});"
        cls = f"message-{log_message[0]}"
        return log_message_bitno, log_message_s, log_message_no, style, cls

    (
        log_message_bitno,
        log_message_s,
        log_message_no,
        style,
        cls,
    ) = next_log_message(log_message_iter)

    bit_to_log_message = {}
    for bit_number in range(0, len(data) * 8):
        # is bit_number still lower than the current log message?
        # rewind otherwise
        while bit_number >= log_message_bitno:
            (
                log_message_bitno,
                log_message_s,
                log_message_no,
                style,
                cls,
            ) = next_log_message(log_message_iter)
        el = S(style=style, title=log_message_s)
        el.classList.add(cls)
        el.classList.add(f"bit-{bit_number}")
        el.bind("mouseenter", el_mouseenter)
        el.bind("mouseleave", el_mouseleave)
        bit_to_log_message[bit_number] = el
    return bit_to_log_message


def get_bytes_per_line():
    """Return bytes per hexdump line based on viewport width."""
    from browser import window  # pylint: disable=import-outside-toplevel
    w = window.innerWidth
    # 4 bytes/line = ~66 chars, 2 bytes/line = ~38 chars
    # At 9px mono (~5.4px/char): 66*5.4=356, 38*5.4=205
    return 2 if w < 500 else 4


def print_hexdump(data: bytes) -> None:
    """Print an interactive hexdump with binary representation and ASCII
    representation of the data, allowing to highlight bits in the hexdump
    and see the corresponding log messages."""
    hd = document["hexdump"]
    hd.clear()

    bpl = get_bytes_per_line()
    bit_to_log_message = gen_bit_to_log_message(data, log_messages)
    byte_number = 0
    for i in range(0, len(data), bpl):
        b = data[i : i + bpl]
        # print offset
        hd <= S(f"{i:08x}  ")
        # print hex
        for c in b:
            hd <= S(f"{c:02x} ")
        # align hex
        for _ in range(bpl - len(b)):
            hd <= S("   ")
        hd <= S(" [")
        # print binary - this is the complex part
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
        for _ in range(bpl - len(b)):
            hd <= S("         ")
        hd <= S("] ")
        # print ASCII
        for c in b:
            if c < 32 or c > 126:
                hd <= S(".")
            else:
                hd <= S(chr(c))
        hd <= BR()


def visualize_huffman(huff1, table_class, is_first=True):
    huffmans = document[table_class]
    huffmans.clear()

    huff_table = H.TABLE()

    header_row = H.TR()
    header_row <= H.TH("Symbol")
    header_row <= H.TH("Code")
    huff_table <= header_row

    for huff in sorted(huff1.table, key=lambda h: h.reverse_symbol):
        huff_row = H.TR()
        rev = str(huff.reverse_symbol)
        # add huffman_{reverse_symbol} class to the row
        huff_row.classList.add(f"huffman-{huff.reverse_symbol}")
        rev += f' (0x{huff.reverse_symbol:02X})'
        huff_row <= H.TD(rev)
        code = str(huff.code)
        if is_first:
            # add chr(huff.code) if it's a printable character
            if huff.code < 256:
                c = chr(huff.code)
                code += f" ({repr(c)})"
            elif huff.code == 256:
                code = "EOF"
            else:
                try:
                    extra = pyflate.extra_length_bits(huff.code)
                    base = pyflate.length_base(huff.code)
                    code += f" (extra {extra}B, base {base})"
                except:
                    code = '(UNUSED?)'
        huff_row <= H.TD(code)
        huff_table <= huff_row

    huffmans <= huff_table


def loading_done():
    loading_label = document["loading_label"]
    loading_label.text = ""
    help_button = document["help_button"]
    help_button.disabled = False


def run_program(*_, **__) -> None:
    """Run the program. This function is called when the input changes and
    when the page is loaded."""
    # pylint: disable=global-statement
    global bit, log_to_html, log_messages
    loading_done()
    document["output"].text = ""  # Clear previous output
    s = document["input"].value
    # Backup the original log_to_html function and replace it with a no-op
    # function during the dry run.
    #
    # We do the dry run to get the log messages before we print the hexdump.
    log_to_html_copy = log_to_html
    log_to_html = log_noop
    log_messages = collections.defaultdict(list)
    try:
        buf = gzip.compress(s.encode(), mtime=0)
        inp = io.BytesIO(buf)

        # we do a dry run first to get the log messages for hexdump
        bit = pyflate.Bitfield(inp)
        noop = lambda *args: None
        _ = list(pyflate.gzip_main_bitfield(bit, noop))

        # restore the original log_to_html function, re-run the program
        # and print the hexdump
        log_to_html = log_to_html_copy
        inp = io.BytesIO(buf)
        bit = pyflate.Bitfield(inp)
        print_hexdump(buf)
        huff1, huff2 = pyflate.gzip_main_bitfield(bit, noop)
        visualize_huffman(huff1, "huffman_browser_table1")
        visualize_huffman(huff2, "huffman_browser_table2", is_first=False)

        # Print the compression result
        diff = len(buf) - len(s)
        sign = "+" if diff > 0 else ""
        ratio = len(buf) / len(s)
        color = "#f06868" if diff > 0 else "#5ccf8a"
        cr = document["compression_result"]
        cr.clear()
        cr <= S(f"{len(s)}B \u2192 {len(buf)}B ")
        cr <= S(f"({sign}{diff}B, \u00d7{ratio:.2f})", style=f"color:{color}")
    except Exception as e:
        # In case of error, clear the hexdump and log the error message to
        # the output area. It might be relevant to log the traceback as well.
        document["hexdump"].clear()
        log_to_html = log_to_html_copy
        log(f"Error: {e}")
        log(traceback.format_exc())
    finally:
        # Always restore the original log_to_html function so that the
        # next invocation of run_program() works as expected.
        log_to_html = log_to_html_copy


pyflate.huffman.log = log
pyflate.log = log
run_program()
document["input"].bind("input", run_program)
