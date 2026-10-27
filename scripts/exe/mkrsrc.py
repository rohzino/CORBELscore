"""Windows resources without outside tools.

    python3 mkrsrc.py icon.ico out.syso --version 2.0.0.4       a resource object for the Go linker
    python3 mkrsrc.py icon.ico out.exe --patch electron.exe ...  the same icon and version in a built .exe
"""
import argparse, struct

RT_ICON, RT_GROUP_ICON, RT_VERSION, RT_MANIFEST = 3, 14, 16, 24
LANG = 0x0409

MANIFEST = b'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<assembly xmlns="urn:schemas-microsoft-com:asm.v1" manifestVersion="1.0">
  <assemblyIdentity type="win32" name="CORBELscore.Launcher" version="1.0.0.0" processorArchitecture="amd64"/>
  <trustInfo xmlns="urn:schemas-microsoft-com:asm.v3"><security><requestedPrivileges>
    <requestedExecutionLevel level="asInvoker" uiAccess="false"/>
  </requestedPrivileges></security></trustInfo>
  <compatibility xmlns="urn:schemas-microsoft-com:compatibility.v1"><application>
    <supportedOS Id="{8e0f7a12-bfb3-4fe8-b9a5-48fd50a15a9a}"/>
  </application></compatibility>
  <application xmlns="urn:schemas-microsoft-com:asm.v3"><windowsSettings>
    <dpiAware xmlns="http://schemas.microsoft.com/SMI/2005/WindowsSettings">true/pm</dpiAware>
    <dpiAwareness xmlns="http://schemas.microsoft.com/SMI/2016/WindowsSettings">PerMonitorV2</dpiAwareness>
  </windowsSettings></application>
  <dependency><dependentAssembly>
    <assemblyIdentity type="win32" name="Microsoft.Windows.Common-Controls" version="6.0.0.0" processorArchitecture="*" publicKeyToken="6595b64144ccf1df" language="*"/>
  </dependentAssembly></dependency>
</assembly>
'''

def read_ico(path):
    data = open(path, "rb").read()
    _, typ, count = struct.unpack_from("<HHH", data, 0)
    assert typ == 1, "not an .ico"
    images = []
    for i in range(count):
        w, h, colors, _, planes, bits, size, off = struct.unpack_from("<BBBBHHII", data, 6 + 16 * i)
        images.append(((w, h, colors, planes, bits, size), data[off:off + size]))
    return images

def pad4(b): return b + b"\0" * (-len(b) % 4)

def vs_block(key, value=b"", children=b"", text=False):
    """One VS_VERSIONINFO-style block: wLength, wValueLength, wType, szKey, padding, value, padding, children."""
    k = (key + "\0").encode("utf-16-le")
    head_len = 6 + len(k)
    body = b"\0" * (-head_len % 4) + value
    if children:
        body = pad4(body) + children
    total = head_len + len(body)
    vlen = len(value) // 2 if text else len(value)
    return pad4(struct.pack("<HHH", total, vlen, 1 if text else 0) + k + body)

def version_info(ver, product, company, description, copyright_):
    nums = [int(x) for x in (ver.split(".") + ["0"] * 4)[:4]]
    ms, ls = (nums[0] << 16) | nums[1], (nums[2] << 16) | nums[3]
    fixed = struct.pack("<13I", 0xFEEF04BD, 0x00010000, ms, ls, ms, ls, 0x3F, 0, 0x4, 0x1, 0, 0, 0)
    s = lambda k, v: vs_block(k, (v + "\0").encode("utf-16-le"), text=True)
    strings = b"".join([s("CompanyName", company), s("FileDescription", description), s("FileVersion", ver),
                        s("InternalName", product), s("LegalCopyright", copyright_), s("OriginalFilename", product + ".exe"),
                        s("ProductName", product), s("ProductVersion", ver)])
    table = vs_block("040904b0", children=strings, text=True)
    sfi = vs_block("StringFileInfo", children=table, text=True)
    var = vs_block("Translation", struct.pack("<HH", LANG, 1200))
    vfi = vs_block("VarFileInfo", children=var, text=True)
    return vs_block("VS_VERSION_INFO", fixed, sfi + vfi)

def build(items, base_rva=0):
    """items: [(type, id, lang, bytes)] -> (section bytes, offsets of the RVA fields).
    With base_rva the RVAs are final (a section added to a linked .exe); without,
    they are offsets the linker relocates (a .syso)."""
    tree = {}
    for t, i, lang, data in items:
        tree.setdefault(t, {}).setdefault(i, {})[lang] = data
    types = sorted(tree)
    def dir_size(n): return 16 + 8 * n
    off = dir_size(len(types))
    type_off, name_off, entry_off, data_off = {}, {}, {}, {}
    for t in types:
        type_off[t] = off; off += dir_size(len(tree[t]))
    for t in types:
        for i in sorted(tree[t]):
            name_off[(t, i)] = off; off += dir_size(len(tree[t][i]))
    for t in types:
        for i in sorted(tree[t]):
            for lang in sorted(tree[t][i]):
                entry_off[(t, i, lang)] = off; off += 16
    for t in types:
        for i in sorted(tree[t]):
            for lang in sorted(tree[t][i]):
                off += -off % 8
                data_off[(t, i, lang)] = off; off += len(tree[t][i][lang])
    sec = bytearray(off + (-off % 8))
    relocs = []
    def put_dir(at, entries):
        struct.pack_into("<IIHHHH", sec, at, 0, 0, 0, 0, 0, len(entries))
        for k, (ident, target) in enumerate(entries):
            struct.pack_into("<II", sec, at + 16 + 8 * k, ident, target)
    put_dir(0, [(t, 0x80000000 | type_off[t]) for t in types])
    for t in types:
        put_dir(type_off[t], [(i, 0x80000000 | name_off[(t, i)]) for i in sorted(tree[t])])
        for i in sorted(tree[t]):
            put_dir(name_off[(t, i)], [(lang, entry_off[(t, i, lang)]) for lang in sorted(tree[t][i])])
            for lang in sorted(tree[t][i]):
                data = tree[t][i][lang]
                struct.pack_into("<IIII", sec, entry_off[(t, i, lang)], base_rva + data_off[(t, i, lang)], len(data), 0, 0)
                relocs.append(entry_off[(t, i, lang)])
                sec[data_off[(t, i, lang)]:data_off[(t, i, lang)] + len(data)] = data
    return bytes(sec), relocs

def coff(section, relocs):
    IMAGE_FILE_MACHINE_AMD64, IMAGE_REL_AMD64_ADDR32NB = 0x8664, 3
    hdr_size, sec_hdr = 20, 40
    raw_ptr = hdr_size + sec_hdr
    reloc_ptr = raw_ptr + len(section)
    sym_ptr = reloc_ptr + 10 * len(relocs)
    out = struct.pack("<HHIIIHH", IMAGE_FILE_MACHINE_AMD64, 1, 0, sym_ptr, 1, 0, 0)
    out += struct.pack("<8sIIIIIIHHI", b".rsrc\0\0\0", 0, 0, len(section), raw_ptr, reloc_ptr, 0, len(relocs), 0, 0x40000040)
    out += section
    for r in relocs:
        out += struct.pack("<IIH", r, 0, IMAGE_REL_AMD64_ADDR32NB)
    out += struct.pack("<8sIhHBB", b".rsrc\0\0\0", 0, 1, 0, 3, 0)   # the section symbol
    out += struct.pack("<I", 4)                                      # empty string table
    return out

# ---- patching a linked .exe (the Electron runtime) ----------------------------------

def pe_layout(d):
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    assert d[pe:pe + 4] == b"PE\0\0", "not a PE file"
    nsec = struct.unpack_from("<H", d, pe + 6)[0]
    optsz = struct.unpack_from("<H", d, pe + 20)[0]
    opt = pe + 24
    assert struct.unpack_from("<H", d, opt)[0] == 0x20B, "only 64-bit executables"
    secs = []
    for k in range(nsec):
        o = opt + optsz + 40 * k
        vsize, va, rawsz, rawptr = struct.unpack_from("<IIII", d, o + 8)
        secs.append((o, va, vsize, rawptr, rawsz))
    return pe, nsec, optsz, opt, secs

def read_resources(d):
    pe, nsec, optsz, opt, secs = pe_layout(d)
    rva = struct.unpack_from("<I", d, opt + 112 + 8 * 2)[0]
    def off(r):
        for _, va, vs, rp, rs in secs:
            if va <= r < va + max(vs, rs): return rp + r - va
        raise ValueError(hex(r))
    base = off(rva)
    def entries(at):
        named, ids = struct.unpack_from("<HH", d, base + at + 12)
        out = [struct.unpack_from("<II", d, base + at + 16 + 8 * k) for k in range(named + ids)]
        assert not any(n & 0x80000000 for n, _ in out), "named resources are not supported"
        return out
    items = []
    for t, toff in entries(0):
        for i, noff in entries(toff & 0x7FFFFFFF):
            for lang, eoff in entries(noff & 0x7FFFFFFF):
                drva, size = struct.unpack_from("<II", d, base + eoff)
                items.append((t, i, lang, d[off(drva):off(drva) + size]))
    return items

def patch(exe_in, exe_out, icons, version):
    """Give a linked .exe new icons and version text, keeping every other resource.
    The new resources go in a section added at the end; the old ones stay, unused."""
    d = bytearray(open(exe_in, "rb").read())
    pe, nsec, optsz, opt, secs = pe_layout(d)
    assert struct.unpack_from("<II", d, opt + 112 + 8 * 4) == (0, 0), "signed executables cannot be patched"
    sect_align, file_align = struct.unpack_from("<II", d, opt + 32)
    end_raw = max(rp + rs for _, _, _, rp, rs in secs)
    assert end_raw == len(d), "data after the last section"
    hdr_end = opt + optsz + 40 * nsec
    assert hdr_end + 40 <= min(rp for _, _, _, rp, _ in secs if rp), "no room for another section header"
    keep = [x for x in read_resources(bytes(d)) if x[0] not in (RT_ICON, RT_GROUP_ICON, RT_VERSION)]
    items = keep + [(RT_ICON, n, LANG, img) for n, (_, img) in enumerate(icons, start=1)]
    items.append((RT_GROUP_ICON, 1, LANG, group_icon(icons)))
    items.append((RT_VERSION, 1, LANG, version))
    new_rva = max(va + max(vs, rs) for _, va, vs, _, rs in secs)
    new_rva += -new_rva % sect_align
    sec, _ = build(items, base_rva=new_rva)
    raw = sec + b"\0" * (-len(sec) % file_align)
    struct.pack_into("<8sIIIIIIHHI", d, hdr_end, b".rsrc2\0\0", len(sec), new_rva, len(raw), len(d), 0, 0, 0, 0, 0x40000040)
    struct.pack_into("<H", d, pe + 6, nsec + 1)
    size_of_image = new_rva + len(sec) + (-len(sec) % sect_align)
    struct.pack_into("<I", d, opt + 56, size_of_image)
    init = struct.unpack_from("<I", d, opt + 8)[0]
    struct.pack_into("<I", d, opt + 8, init + len(raw))
    struct.pack_into("<I", d, opt + 64, 0)                         # checksum: not needed for programs
    struct.pack_into("<II", d, opt + 112 + 8 * 2, new_rva, len(sec))
    d += raw
    open(exe_out, "wb").write(d)

def group_icon(icons):
    g = struct.pack("<HHH", 0, 1, len(icons))
    for n, ((w, h, colors, planes, bits, size), _) in enumerate(icons, start=1):
        g += struct.pack("<BBBBHHIH", w, h, colors, 0, planes, bits, size, n)
    return g

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ico"); ap.add_argument("out")
    ap.add_argument("--patch", help="an existing .exe to give the icon and version (written to out)")
    ap.add_argument("--version", default="1.0.0.0"); ap.add_argument("--product", default="CORBELscore")
    ap.add_argument("--company", default="CORBELscore"); ap.add_argument("--description", default="CORBELscore")
    ap.add_argument("--copyright", default="")
    a = ap.parse_args()
    icons = read_ico(a.ico)
    ver = version_info(a.version, a.product, a.company, a.description, a.copyright)
    if a.patch:
        patch(a.patch, a.out, icons, ver)
        print(f"{a.out}: {len(icons)} icon sizes, version {a.version}, other resources kept")
        return
    items = [(RT_MANIFEST, 1, LANG, MANIFEST), (RT_VERSION, 1, LANG, ver), (RT_GROUP_ICON, 1, LANG, group_icon(icons))]
    items += [(RT_ICON, n, LANG, img) for n, (_, img) in enumerate(icons, start=1)]
    sec, rel = build(items)
    open(a.out, "wb").write(coff(sec, rel))
    print(f"{a.out}: {len(icons)} icon sizes, manifest, version {a.version}")

if __name__ == "__main__":
    main()
