"""Disassembles one Project Zomboid method, instruction by instruction.

    python tools/javadis.py zombie.iso.objects.IsoTrap drawCircleExplosion

The third tool in the set, and the one that answers the question the other two
cannot:

    pzapi.py    does this method exist, and is it public?
    javarefs.py what does it touch?  (bytecode order, no branches)
    javadis.py  **under what condition?**

That distinction has cost this project two designs. `BaseVehicle.update()`
calls `setZ(0)` and then `setZ(level)`, and javarefs shows both -- but only a
real disassembly shows that the first is unconditional and the second sits
behind a floor check, which is the whole reason flight is "driving on an
invisible floor" instead of a lifted physics body (PILOTING.md). `setGodMod`
looks callable and silently refuses without a role capability. Reading a list
of references as if it were control flow is how both were nearly got wrong.

DEV_GUIDE says "the bytecode is the documentation". This makes it readable:
branch targets are resolved to bci numbers, constant-pool references to real
names, and jump destinations are marked, so an `if (mode == Explosion)` is
visible as a branch rather than inferred from two names being near each other.
"""
import re
import struct
import sys
import zipfile

JAR = (r"C:\Program Files (x86)\Steam\steamapps\common"
       r"\ProjectZomboid\projectzomboid.jar")

# (mnemonic, operand length in bytes). None marks the three variable-length
# instructions, which are handled separately.
OPS = {
    0x00: ("nop", 0), 0x01: ("aconst_null", 0),
    0x02: ("iconst_m1", 0), 0x03: ("iconst_0", 0), 0x04: ("iconst_1", 0),
    0x05: ("iconst_2", 0), 0x06: ("iconst_3", 0), 0x07: ("iconst_4", 0),
    0x08: ("iconst_5", 0), 0x09: ("lconst_0", 0), 0x0a: ("lconst_1", 0),
    0x0b: ("fconst_0", 0), 0x0c: ("fconst_1", 0), 0x0d: ("fconst_2", 0),
    0x0e: ("dconst_0", 0), 0x0f: ("dconst_1", 0),
    0x10: ("bipush", 1), 0x11: ("sipush", 2),
    0x12: ("ldc", 1), 0x13: ("ldc_w", 2), 0x14: ("ldc2_w", 2),
    0x15: ("iload", 1), 0x16: ("lload", 1), 0x17: ("fload", 1),
    0x18: ("dload", 1), 0x19: ("aload", 1),
    0x36: ("istore", 1), 0x37: ("lstore", 1), 0x38: ("fstore", 1),
    0x39: ("dstore", 1), 0x3a: ("astore", 1),
    0x84: ("iinc", 2),
    0xbc: ("newarray", 1), 0xa9: ("ret", 1),
    # field and method references -- the interesting ones
    0xb2: ("getstatic", 2), 0xb3: ("putstatic", 2),
    0xb4: ("getfield", 2), 0xb5: ("putfield", 2),
    0xb6: ("invokevirtual", 2), 0xb7: ("invokespecial", 2),
    0xb8: ("invokestatic", 2), 0xb9: ("invokeinterface", 4),
    0xba: ("invokedynamic", 4),
    0xbb: ("new", 2), 0xbd: ("anewarray", 2),
    0xc0: ("checkcast", 2), 0xc1: ("instanceof", 2),
    0xc5: ("multianewarray", 3),
    0xc6: ("ifnull", 2), 0xc7: ("ifnonnull", 2),
    0xc8: ("goto_w", 4), 0xc9: ("jsr_w", 4),
    0xaa: ("tableswitch", None), 0xab: ("lookupswitch", None),
    0xc4: ("wide", None),
}
# simple no-operand instructions
for _op, _name in {
    0x1a: "iload_0", 0x1b: "iload_1", 0x1c: "iload_2", 0x1d: "iload_3",
    0x1e: "lload_0", 0x1f: "lload_1", 0x20: "lload_2", 0x21: "lload_3",
    0x22: "fload_0", 0x23: "fload_1", 0x24: "fload_2", 0x25: "fload_3",
    0x26: "dload_0", 0x27: "dload_1", 0x28: "dload_2", 0x29: "dload_3",
    0x2a: "aload_0", 0x2b: "aload_1", 0x2c: "aload_2", 0x2d: "aload_3",
    0x2e: "iaload", 0x2f: "laload", 0x30: "faload", 0x31: "daload",
    0x32: "aaload", 0x33: "baload", 0x34: "caload", 0x35: "saload",
    0x3b: "istore_0", 0x3c: "istore_1", 0x3d: "istore_2", 0x3e: "istore_3",
    0x3f: "lstore_0", 0x40: "lstore_1", 0x41: "lstore_2", 0x42: "lstore_3",
    0x43: "fstore_0", 0x44: "fstore_1", 0x45: "fstore_2", 0x46: "fstore_3",
    0x47: "dstore_0", 0x48: "dstore_1", 0x49: "dstore_2", 0x4a: "dstore_3",
    0x4b: "astore_0", 0x4c: "astore_1", 0x4d: "astore_2", 0x4e: "astore_3",
    0x4f: "iastore", 0x50: "lastore", 0x51: "fastore", 0x52: "dastore",
    0x53: "aastore", 0x54: "bastore", 0x55: "castore", 0x56: "sastore",
    0x57: "pop", 0x58: "pop2", 0x59: "dup", 0x5a: "dup_x1", 0x5b: "dup_x2",
    0x5c: "dup2", 0x5d: "dup2_x1", 0x5e: "dup2_x2", 0x5f: "swap",
    0x60: "iadd", 0x61: "ladd", 0x62: "fadd", 0x63: "dadd",
    0x64: "isub", 0x65: "lsub", 0x66: "fsub", 0x67: "dsub",
    0x68: "imul", 0x69: "lmul", 0x6a: "fmul", 0x6b: "dmul",
    0x6c: "idiv", 0x6d: "ldiv", 0x6e: "fdiv", 0x6f: "ddiv",
    0x70: "irem", 0x71: "lrem", 0x72: "frem", 0x73: "drem",
    0x74: "ineg", 0x75: "lneg", 0x76: "fneg", 0x77: "dneg",
    0x78: "ishl", 0x79: "lshl", 0x7a: "ishr", 0x7b: "lshr",
    0x7c: "iushr", 0x7d: "lushr", 0x7e: "iand", 0x7f: "land",
    0x80: "ior", 0x81: "lor", 0x82: "ixor", 0x83: "lxor",
    0x85: "i2l", 0x86: "i2f", 0x87: "i2d", 0x88: "l2i", 0x89: "l2f",
    0x8a: "l2d", 0x8b: "f2i", 0x8c: "f2l", 0x8d: "f2d", 0x8e: "d2i",
    0x8f: "d2l", 0x90: "d2f", 0x91: "i2b", 0x92: "i2c", 0x93: "i2s",
    0x94: "lcmp", 0x95: "fcmpl", 0x96: "fcmpg", 0x97: "dcmpl", 0x98: "dcmpg",
    0xac: "ireturn", 0xad: "lreturn", 0xae: "freturn", 0xaf: "dreturn",
    0xb0: "areturn", 0xb1: "return",
    0xbe: "arraylength", 0xbf: "athrow",
    0xc2: "monitorenter", 0xc3: "monitorexit",
}.items():
    OPS[_op] = (_name, 0)
# branches: 2-byte signed offset from the instruction's own bci
BRANCH = {
    0x99: "ifeq", 0x9a: "ifne", 0x9b: "iflt", 0x9c: "ifge", 0x9d: "ifgt",
    0x9e: "ifle", 0x9f: "if_icmpeq", 0xa0: "if_icmpne", 0xa1: "if_icmplt",
    0xa2: "if_icmpge", 0xa3: "if_icmpgt", 0xa4: "if_icmple",
    0xa5: "if_acmpeq", 0xa6: "if_acmpne", 0xa7: "goto", 0xa8: "jsr",
    0xc6: "ifnull", 0xc7: "ifnonnull",
}
for _op, _name in BRANCH.items():
    OPS[_op] = (_name, 2)


def parse_pool(data, i):
    """Returns (constant pool as a list, offset after it)."""
    count = struct.unpack_from(">H", data, i)[0]
    i += 2
    pool = [None] * count
    n = 1
    while n < count:
        tag = data[i]
        if tag == 1:                                   # Utf8
            ln = struct.unpack_from(">H", data, i + 1)[0]
            pool[n] = data[i + 3:i + 3 + ln].decode("utf-8", "replace")
            i += 3 + ln
        elif tag in (7, 8, 16, 19, 20):                # single u2 index
            pool[n] = (tag, struct.unpack_from(">H", data, i + 1)[0])
            i += 3
        elif tag == 15:                                # MethodHandle
            pool[n] = (tag, data[i + 1],
                       struct.unpack_from(">H", data, i + 2)[0])
            i += 4
        elif tag in (3, 4):                            # int, float
            pool[n] = (tag, struct.unpack_from(">I", data, i + 1)[0])
            i += 5
        elif tag in (5, 6):                            # long, double
            pool[n] = (tag, 0)
            i += 9
            n += 1                                     # takes two slots
        else:                                          # 9,10,11,12,17,18
            pool[n] = (tag, struct.unpack_from(">H", data, i + 1)[0],
                       struct.unpack_from(">H", data, i + 3)[0])
            i += 5
        n += 1
    return pool, i


def resolve(pool, idx):
    """Renders a constant-pool entry the way a human reads it."""
    e = pool[idx]
    if e is None:
        return f"#{idx}"
    if isinstance(e, str):
        return f'"{e}"'
    tag = e[0]
    if tag == 7:                                       # Class
        return pool[e[1]].replace("/", ".").split(".")[-1]
    if tag == 8:                                       # String
        return f'"{pool[e[1]]}"'
    if tag in (9, 10, 11):                             # Field/Method/Interface
        cls = pool[pool[e[1]][1]].replace("/", ".").split(".")[-1]
        nt = pool[e[2]]
        return f"{cls}.{pool[nt[1]]}{pool[nt[2]]}"
    if tag == 3:
        return str(struct.unpack(">i", struct.pack(">I", e[1]))[0])
    if tag == 4:
        return str(struct.unpack(">f", struct.pack(">I", e[1]))[0])
    return f"#{idx}"


def code_of(data, pool, i, want):
    """Walks the method table and yields (name, descriptor, code bytes)."""
    out = []
    count = struct.unpack_from(">H", data, i)[0]
    i += 2
    for _ in range(count):
        _flags, name_i, desc_i, n_attr = struct.unpack_from(">HHHH", data, i)
        i += 8
        name, desc = pool[name_i], pool[desc_i]
        code = None
        for _ in range(n_attr):
            a_name = pool[struct.unpack_from(">H", data, i)[0]]
            a_len = struct.unpack_from(">I", data, i + 2)[0]
            body = data[i + 6:i + 6 + a_len]
            if a_name == "Code":
                clen = struct.unpack_from(">I", body, 4)[0]
                code = body[8:8 + clen]
            i += 6 + a_len
        if code and (want in name or want in (name + desc)):
            out.append((name, desc, code))
    return out


def disassemble(code, pool):
    """Returns [(bci, mnemonic, rendered operand, branch target or None)]."""
    out, i = [], 0
    while i < len(code):
        bci, op = i, code[i]
        i += 1
        if op == 0xc4:                                 # wide
            op2 = code[i]
            n = 4 if op2 == 0x84 else 2
            out.append((bci, "wide " + OPS.get(op2, ("?", 0))[0], "", None))
            i += 1 + n
            continue
        if op in (0xaa, 0xab):                         # switches
            pad = (4 - (i % 4)) % 4
            i += pad
            default = struct.unpack_from(">i", code, i)[0]
            if op == 0xaa:
                lo, hi = struct.unpack_from(">ii", code, i + 4)
                n = hi - lo + 1
                i += 12 + 4 * n
            else:
                n = struct.unpack_from(">i", code, i + 4)[0]
                i += 8 + 8 * n
            out.append((bci, OPS[op][0], f"{n} case(s)", bci + default))
            continue
        name, nbytes = OPS.get(op, (f"op_0x{op:02x}", 0))
        raw = code[i:i + nbytes]
        i += nbytes
        target, text = None, ""
        if op in BRANCH:
            off = struct.unpack(">h", raw)[0]
            target = bci + off
            text = f"-> {target}"
        elif op in (0xc8, 0xc9):
            target = bci + struct.unpack(">i", raw)[0]
            text = f"-> {target}"
        elif nbytes >= 2 and op in (
                0x12, 0x13, 0x14, 0xb2, 0xb3, 0xb4, 0xb5, 0xb6, 0xb7,
                0xb8, 0xb9, 0xba, 0xbb, 0xbd, 0xc0, 0xc1, 0xc5):
            text = resolve(pool, struct.unpack_from(">H", raw, 0)[0])
        elif op == 0x12:
            text = resolve(pool, raw[0])
        elif nbytes:
            text = " ".join(str(b) for b in raw)
        if op == 0x12 and nbytes == 1:
            text = resolve(pool, raw[0])
        out.append((bci, name, text, target))
    return out


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(2)
    cls, want = sys.argv[1], sys.argv[2]
    with zipfile.ZipFile(JAR) as z:
        data = z.read(cls.replace(".", "/") + ".class")
    # magic(4) minor(2) major(2) then the pool; after it come
    # access(2) this(2) super(2) interfaces_count(2) interfaces(2n).
    pool, i = parse_pool(data, 8)
    i += 8 + 2 * struct.unpack_from(">H", data, i + 6)[0]
    n_fields = struct.unpack_from(">H", data, i)[0]
    i += 2
    for _ in range(n_fields):                               # skip fields
        n_attr = struct.unpack_from(">H", data, i + 6)[0]
        i += 8
        for _ in range(n_attr):
            i += 6 + struct.unpack_from(">I", data, i + 2)[0]

    found = code_of(data, pool, i, want)
    if not found:
        print(f"no method matching {want!r} in {cls}")
        sys.exit(1)
    for name, desc, code in found:
        print(f"\n{name}{desc}")
        ins = disassemble(code, pool)
        targets = {t for _, _, _, t in ins if t is not None}
        for bci, mnem, text, _ in ins:
            mark = ">>" if bci in targets else "  "
            print(f"  {mark} {bci:5d}  {mnem:<16} {text}")


if __name__ == "__main__":
    main()
