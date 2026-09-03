#!/usr/bin/env python3
"""
analyze_minidump.py - blame a Windows kernel minidump WITHOUT installing WinDbg.

Reads a 64-bit kernel minidump (C:\\Windows\\Minidump\\*.dmp), prints the bugcheck,
maps the faulting address and every return address on the crashed thread's stack
to the driver that owns it, lists recently UNLOADED drivers (a fault inside one =
a device was yanked mid-use), and - when the local copy of the faulting module
matches the dump's build - fetches the matching PDB from Microsoft's public symbol
server and names the exact function (plus a disassembly of the fault site if the
optional `capstone` package is installed).

Used on 2026-09-03 to show that the field PC's two 0x1E crashes were the kernel
scheduler (nt!KiAbProcessPostContextSwitch+0x41), not a USB driver.

Usage (read-only; touches nothing but its own symbol cache):
    python analyze_minidump.py <dump.dmp> [more.dmp ...] [--no-symbols] [--cache DIR]

C:\\Windows\\Minidump is admin-only. Copy the dumps out first from an ELEVATED shell:
    Copy-Item C:\\Windows\\Minidump\\*.dmp <some folder you can read>
Symbol cache default: %LOCALAPPDATA%\\FieldRig\\symbols  (PDBs are ~10 MB each).
"""
import argparse
import ctypes
import ctypes.wintypes as W
import os
import struct
import sys
import urllib.request
import uuid

KVA_LO = 0xFFFF800000000000
SYSTEM32 = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32")


def is_kva(x):
    return x >= KVA_LO


# ----------------------------------------------------------------- dump ------

class Dump:
    """The pieces of a triage (mini) dump we need. Offsets verified against real
    dumps from Win11 25H2 (26200); every field is sanity-checked on load."""

    def __init__(self, path):
        self.path = path
        d = self.d = open(path, "rb").read()
        if d[:8] != b"PAGEDU64":
            raise ValueError("not a 64-bit kernel dump (no PAGEDU64 signature)")
        self.bugcheck = struct.unpack_from("<I", d, 0x38)[0]
        self.params = struct.unpack_from("<4Q", d, 0x40)
        t = struct.unpack_from("<18I", d, 0x2000)          # TRIAGE_DUMP64
        self.ctx_off, self.exc_off, self.unl_off = t[3], t[4], t[6]
        self.cs_off, self.cs_size = t[10], t[11]
        self.drv_off, self.drv_cnt = t[12], t[13]
        self.drivers = self._drivers()
        self.unloaded = self._unloaded()
        self.rip = struct.unpack_from("<Q", d, self.ctx_off + 0xF8)[0]
        self.exc_code = struct.unpack_from("<I", d, self.exc_off)[0]
        self.exc_addr = struct.unpack_from("<Q", d, self.exc_off + 0x10)[0]

    def _string(self, off):
        n = struct.unpack_from("<I", self.d, off)[0]
        return self.d[off + 4:off + 4 + 2 * n].decode("utf-16-le", "replace")

    def _drivers(self):
        # DUMP_DRIVER_ENTRY64, stride 0x90: +0 name-string offset, +0x38 DllBase,
        # +0x48 SizeOfImage, +0x88 TimeDateStamp. EntryPoint is 0 in triage dumps.
        out = []
        for i in range(self.drv_cnt):
            e = self.drv_off + i * 0x90
            name_off = struct.unpack_from("<Q", self.d, e)[0]
            base = struct.unpack_from("<Q", self.d, e + 0x38)[0]
            size = struct.unpack_from("<I", self.d, e + 0x48)[0]
            tds = struct.unpack_from("<I", self.d, e + 0x88)[0]
            if not (is_kva(base) and 0x1000 <= size <= 0x8000000 and name_off < len(self.d)):
                raise ValueError(f"driver entry {i} failed sanity check - dump layout changed?")
            name = os.path.basename(self._string(name_off).replace("\\", "/"))
            out.append((base, size, name, tds))
        return out

    def _unloaded(self):
        # ULONG Count; then {UNICODE_STRING64 Name; WCHAR Buf[12]; ULONG64 Start, End}
        d, off = self.d, self.unl_off
        if not off or off + 4 > len(d):
            return []
        cnt = struct.unpack_from("<I", d, off)[0]
        if cnt > 64:
            return []
        for align in (8, 4):
            p, tmp, ok = off + align, [], True
            for _ in range(cnt):
                if p + 56 > len(d):
                    ok = False
                    break
                ln = struct.unpack_from("<H", d, p)[0]
                nm = d[p + 16:p + 16 + min(ln, 24)].decode("utf-16-le", "replace").strip("\x00")
                s, e = struct.unpack_from("<2Q", d, p + 40)
                if not (is_kva(s) and is_kva(e) and e > s):
                    ok = False
                    break
                tmp.append((s, e, nm))
                p += 56
            if ok:
                return tmp
        return []

    def module_of(self, addr):
        for base, size, name, _ in self.drivers:
            if base <= addr < base + size:
                return name, base, addr - base
        for s, e, name in self.unloaded:
            if s <= addr < e:
                return f"[UNLOADED] {name}", s, addr - s
        return None

    def stack_addresses(self):
        st = self.d[self.cs_off:self.cs_off + self.cs_size]
        for o in range(0, len(st) - 8, 8):
            v = struct.unpack_from("<Q", st, o)[0]
            m = self.module_of(v)
            if m:
                yield o, v, m


# -------------------------------------------------------------- symbols ------

def pe_info(path):
    """(TimeDateStamp, SizeOfImage, pdb_name, pdb_sig, rva->file-offset fn) of a local PE."""
    d = open(path, "rb").read()
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    ts = struct.unpack_from("<I", d, pe + 8)[0]
    nsec = struct.unpack_from("<H", d, pe + 6)[0]
    optsize = struct.unpack_from("<H", d, pe + 20)[0]
    magic = struct.unpack_from("<H", d, pe + 24)[0]
    size_of_image = struct.unpack_from("<I", d, pe + 24 + 56)[0]
    dd = pe + 24 + (112 if magic == 0x20B else 96)
    dbg_rva, dbg_size = struct.unpack_from("<2I", d, dd + 6 * 8)
    secs = []
    so = pe + 24 + optsize
    for i in range(nsec):
        vs, va, rs, ro = struct.unpack_from("<4I", d, so + i * 40 + 8)
        secs.append((va, vs, ro, rs))

    def r2o(r):
        for va, vs, ro, rs in secs:
            if va <= r < va + max(vs, rs):
                return r - va + ro
        return None

    pdb_name = pdb_sig = None
    o = r2o(dbg_rva)
    if o is not None:
        for i in range(dbg_size // 28):
            typ = struct.unpack_from("<I", d, o + i * 28 + 12)[0]
            sz, _, ptr = struct.unpack_from("<3I", d, o + i * 28 + 16)
            if typ == 2 and d[ptr:ptr + 4] == b"RSDS":
                g = uuid.UUID(bytes_le=d[ptr + 4:ptr + 20])
                age = struct.unpack_from("<I", d, ptr + 20)[0]
                pdb_name = d[ptr + 24:ptr + sz].split(b"\0")[0].decode()
                pdb_sig = f"{str(g).replace('-', '').upper()}{age:X}"
    return ts, size_of_image, pdb_name, pdb_sig, r2o, d


def find_local_image(name):
    for cand in (os.path.join(SYSTEM32, name), os.path.join(SYSTEM32, "drivers", name)):
        if os.path.exists(cand):
            return cand
    return None


def fetch_pdb(pdb_name, pdb_sig, cache):
    os.makedirs(cache, exist_ok=True)
    dst = os.path.join(cache, pdb_name)
    if os.path.exists(dst) and os.path.getsize(dst) > 0:
        return dst
    url = f"https://msdl.microsoft.com/download/symbols/{pdb_name}/{pdb_sig}/{pdb_name}"
    req = urllib.request.Request(url, headers={"User-Agent": "Microsoft-Symbol-Server/10.0"})
    with urllib.request.urlopen(req, timeout=180) as r, open(dst + ".part", "wb") as f:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
    os.replace(dst + ".part", dst)
    return dst


class SYMBOL_INFO(ctypes.Structure):
    _fields_ = [("SizeOfStruct", W.ULONG), ("TypeIndex", W.ULONG), ("Reserved", ctypes.c_ulonglong * 2),
                ("Index", W.ULONG), ("Size", W.ULONG), ("ModBase", ctypes.c_ulonglong), ("Flags", W.ULONG),
                ("Value", ctypes.c_ulonglong), ("Address", ctypes.c_ulonglong), ("Register", W.ULONG),
                ("Scope", W.ULONG), ("Tag", W.ULONG), ("NameLen", W.ULONG), ("MaxNameLen", W.ULONG),
                ("Name", ctypes.c_char * 1024)]


class Symbolizer:
    """dbghelp.dll (ships with Windows) + a local PDB directory. No symsrv needed."""

    def __init__(self, cache):
        self.dbg = ctypes.WinDLL(os.path.join(SYSTEM32, "dbghelp.dll"), use_last_error=True)
        self.hp = ctypes.c_void_p(0x1234)
        self.dbg.SymSetOptions(0x2 | 0x10)                       # UNDNAME | LOAD_LINES
        self.dbg.SymInitializeW.argtypes = [ctypes.c_void_p, W.LPCWSTR, W.BOOL]
        if not self.dbg.SymInitializeW(self.hp, cache, False):
            raise OSError("SymInitialize failed")
        f = self.dbg.SymLoadModuleExW
        f.restype = ctypes.c_ulonglong
        f.argtypes = [ctypes.c_void_p, ctypes.c_void_p, W.LPCWSTR, W.LPCWSTR, ctypes.c_ulonglong,
                      W.DWORD, ctypes.c_void_p, W.DWORD]
        self.dbg.SymFromAddr.argtypes = [ctypes.c_void_p, ctypes.c_ulonglong,
                                         ctypes.POINTER(ctypes.c_ulonglong), ctypes.POINTER(SYMBOL_INFO)]
        self.loaded = {}

    def load(self, image_path, base, size):
        if self.dbg.SymLoadModuleExW(self.hp, None, image_path, None, base, size, None, 0):
            self.loaded[base] = image_path
            return True
        return False

    def name(self, addr):
        si = SYMBOL_INFO()
        si.SizeOfStruct = 88                                     # sizeof up to Name[1], x64
        si.MaxNameLen = 1000
        disp = ctypes.c_ulonglong(0)
        if self.dbg.SymFromAddr(self.hp, addr, ctypes.byref(disp), ctypes.byref(si)):
            return f"{si.Name.decode()}+0x{disp.value:x}"
        return None


def try_disasm(image_path, r2o, image_bytes, rva, before=0x48, after=0x30):
    try:
        from capstone import Cs, CS_ARCH_X86, CS_MODE_64
    except ImportError:
        return ["    (pip install capstone for a disassembly of the fault site)"]
    start = max(rva - before, 0)
    off = r2o(start)
    if off is None:
        return []
    code = image_bytes[off:off + before + after]
    out = []
    for ins in Cs(CS_ARCH_X86, CS_MODE_64).disasm(code, start):
        mark = "   <== FAULT" if ins.address == rva else ""
        out.append(f"    +0x{ins.address:x}  {ins.mnemonic:8} {ins.op_str}{mark}")
    return out


# --------------------------------------------------------------- report ------

def analyze(path, symbols=True, cache=None):
    dmp = Dump(path)
    print(f"=== {os.path.basename(path)}  ({len(dmp.d):,} bytes) ===")
    p = dmp.params
    print(f"bugcheck 0x{dmp.bugcheck:X}   p1=0x{p[0]:x}  p2=0x{p[1]:x}  p3=0x{p[2]:x}  p4=0x{p[3]:x}")
    print(f"drivers loaded: {len(dmp.drivers)}   unloaded ring: {len(dmp.unloaded)}   stack bytes: {dmp.cs_size}")

    sym = None
    sym_base = {}
    if symbols:
        cache = cache or os.path.join(os.environ.get("LOCALAPPDATA", "."), "FieldRig", "symbols")
        try:
            sym = Symbolizer(cache)
        except Exception as e:                                   # noqa: BLE001
            print(f"(symbols unavailable: {e})")
            sym = None

    def describe(addr):
        m = dmp.module_of(addr)
        if not m:
            return None
        name, base, off = m
        if sym and base not in sym_base:
            sym_base[base] = False
            local = find_local_image(name.replace("[UNLOADED] ", ""))
            if local:
                try:
                    ts, size, pdb_name, pdb_sig, _, _ = pe_info(local)
                    dump_ts = next((t for b, s, n, t in dmp.drivers if b == base), None)
                    if pdb_name and pdb_sig and ts == dump_ts:
                        fetch_pdb(pdb_name, pdb_sig, cache)
                        sym_base[base] = sym.load(local, base, size)
                except Exception as e:                           # noqa: BLE001
                    print(f"    (no symbols for {name}: {e})")
        if sym_base.get(base):
            s = sym.name(addr)
            if s:
                return f"{name.rsplit('.', 1)[0]}!{s}"
        return f"{name}+0x{off:x}"

    print()
    interesting = [("exception", dmp.exc_addr), ("dump-capture RIP", dmp.rip)]
    for i, x in enumerate(p, 1):
        if is_kva(x):
            interesting.append((f"param{i}", x))
    for label, a in interesting:
        print(f"  {label:18} 0x{a:x}  ->  {describe(a) or '(not in any module)'}")

    print("\nstack (return addresses inside known modules, innermost first):")
    for o, v, _ in dmp.stack_addresses():
        print(f"  [+0x{o:04x}] {describe(v)}")

    if dmp.unloaded:
        print("\nrecently unloaded drivers (ring, oldest first):")
        print("  " + ", ".join(nm for _, _, nm in dmp.unloaded))

    # disassembly of the fault site if it lives in a local, build-matched image
    fault = p[1] if dmp.bugcheck in (0x1E, 0x7E, 0x8E, 0x1000007E) and is_kva(p[1]) else dmp.exc_addr
    m = dmp.module_of(fault)
    if m and not m[0].startswith("[UNLOADED]"):
        local = find_local_image(m[0])
        if local:
            ts, _, _, _, r2o, image_bytes = pe_info(local)
            dump_ts = next((t for b, s, n, t in dmp.drivers if b == m[1]), None)
            if ts == dump_ts:
                print(f"\nfault site disassembly ({m[0]}, local copy matches dump build):")
                for line in try_disasm(local, r2o, image_bytes, m[2]):
                    print(line)
    print()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dumps", nargs="+")
    ap.add_argument("--no-symbols", action="store_true", help="skip PDB download / dbghelp naming")
    ap.add_argument("--cache", help="symbol cache directory")
    a = ap.parse_args()
    rc = 0
    for path in a.dumps:
        try:
            analyze(path, symbols=not a.no_symbols, cache=a.cache)
        except PermissionError:
            print(f"{path}: permission denied - copy it out of C:\\Windows\\Minidump from an elevated shell first")
            rc = 2
        except Exception as e:                                   # noqa: BLE001
            print(f"{path}: FAILED: {e}")
            rc = 2
    sys.exit(rc)


if __name__ == "__main__":
    main()
