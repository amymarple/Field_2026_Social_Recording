<#
.SYNOPSIS
    WASAPI audio capture for the Dodotronic UltraMic384K (or any Windows capture
    endpoint), self-contained in PowerShell 5.1 via an embedded C# class - NO
    ffmpeg, NO Python, NO downloads.

    Why this exists: ffmpeg on Windows can only capture audio through DirectShow,
    and this UltraMic's DirectShow pin is capped at 96 kHz. WASAPI reaches the
    device's true native format.

    Capture mode (-Mode, default auto):
      exclusive - opens the device DIRECTLY at its own declared native format
                  (UltraMic384K_EVO: 384000 Hz / 1 ch / 16-bit PCM), bypassing
                  the Windows audio engine entirely. No resampling, no format
                  surprises, and the mic is locked to this recorder while it
                  runs (desirable for a dedicated field mic).
      shared    - captures at the endpoint's Windows "Default Format" (what
                  Python sounddevice dtype=float32 sees). WARNING: that is
                  whatever the Sound control panel is set to - on this PC it was
                  48000 Hz stereo, which would silently throw away everything
                  ultrasonic. Only use if exclusive mode is unavailable.
      auto      - exclusive first, shared as a loudly-warned fallback.

    Writes clock-aligned WAV segments with the rig's filename contract:
        <Prefix>_YYYY-MM-DD_HH-MM-SS.wav             (open / still recording)
        <Prefix>_YYYY-MM-DD_HH-MM-SS_to_HH-MM-SS.wav (finalized on rollover)
    Files that would exceed 4 GB become RF64 automatically (a JUNK chunk is
    reserved up front and rewritten as ds64 only when needed, so files under
    4 GB stay 100% classic WAV).

.PARAMETER Device
    Substring of the capture endpoint's friendly name (case-insensitive), e.g.
    'UltraMic'. Must match exactly one active capture device.

.PARAMETER OutDir
    Directory for the WAV segments (created if missing).

.PARAMETER Prefix
    Filename prefix, e.g. MIC01.

.PARAMETER SegmentSeconds
    Segment length; rollovers are aligned to the wall clock (3600 = on the hour).

.PARAMETER Seconds
    0 = record until killed (production). >0 = stop after this many seconds
    (test clip; the file is finalized with _to_ like a normal rollover).

.PARAMETER StoreFormat
    int16 (default; matches the UltraMic's 16-bit ADC - lossless, ~2.76 GB/h at
    384 kHz mono) or float32 (verbatim engine floats in shared mode; upconverted
    from int16 in exclusive mode, i.e. 2x disk for no extra information).

.PARAMETER ListDevices
    Print all active capture endpoints (with native + shared formats) and exit.

.NOTES
    Exit codes: 0 ok/test done, 2 fatal (device not found/COM failure),
    3 another capture instance for this Prefix is already running.
    Launched per-mic by ultramic_record.ps1; can also be run standalone.
#>
param(
    [string]$Device = 'UltraMic',
    [string]$OutDir = '',
    [string]$Prefix = 'MIC01',
    [int]$SegmentSeconds = 3600,
    [int]$Seconds = 0,
    [ValidateSet('int16','float32')][string]$StoreFormat = 'int16',
    [ValidateSet('auto','exclusive','shared')][string]$Mode = 'auto',
    [switch]$ListDevices
)

$ErrorActionPreference = 'Stop'

Add-Type -TypeDefinition @'
using System;
using System.IO;
using System.Runtime.InteropServices;
using System.Threading;

namespace UltraMicCap
{
    // ---- minimal WASAPI COM interop -------------------------------------------
    [ComImport, Guid("BCDE0395-E52F-467C-8E3D-C4579291692E")]
    class MMDeviceEnumeratorCom { }

    [ComImport, Guid("A95664D2-9614-4F35-A746-DE8DB63617E6"),
     InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IMMDeviceEnumerator
    {
        [PreserveSig] int EnumAudioEndpoints(int dataFlow, int stateMask, out IMMDeviceCollection devices);
        [PreserveSig] int GetDefaultAudioEndpoint(int dataFlow, int role, out IMMDevice endpoint);
        [PreserveSig] int GetDevice([MarshalAs(UnmanagedType.LPWStr)] string id, out IMMDevice device);
    }

    [ComImport, Guid("0BD7A1BE-7A1A-44DB-8397-CC5392387B5E"),
     InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IMMDeviceCollection
    {
        [PreserveSig] int GetCount(out uint count);
        [PreserveSig] int Item(uint index, out IMMDevice device);
    }

    [ComImport, Guid("D666063F-1587-4E43-81F1-B948E807363F"),
     InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IMMDevice
    {
        [PreserveSig] int Activate(ref Guid iid, int clsCtx, IntPtr activationParams,
                     [MarshalAs(UnmanagedType.IUnknown)] out object iface);
        [PreserveSig] int OpenPropertyStore(int stgmAccess, out IPropertyStore properties);
        [PreserveSig] int GetId([MarshalAs(UnmanagedType.LPWStr)] out string id);
        [PreserveSig] int GetState(out int state);
    }

    [StructLayout(LayoutKind.Sequential)]
    struct PropertyKey { public Guid fmtid; public int pid; }

    // x64 PROPVARIANT: 8-byte header, then the union (BLOB = { ULONG cbSize; BYTE* p; }).
    [StructLayout(LayoutKind.Sequential)]
    struct PropVariant
    {
        public ushort vt; public ushort r1; public ushort r2; public ushort r3;
        public IntPtr p;   // VT_LPWSTR: string ptr | VT_BLOB: cbSize in low 32 bits
        public IntPtr p2;  // VT_BLOB: data ptr
    }

    [ComImport, Guid("886d8eeb-8cf2-4446-8d02-cdba1dbdcf99"),
     InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IPropertyStore
    {
        [PreserveSig] int GetCount(out int count);
        [PreserveSig] int GetAt(int index, out PropertyKey key);
        [PreserveSig] int GetValue(ref PropertyKey key, out PropVariant value);
        [PreserveSig] int SetValue(ref PropertyKey key, ref PropVariant value);
        [PreserveSig] int Commit();
    }

    [ComImport, Guid("1CB9AD4C-DBFA-4c32-B178-C2F568A703B2"),
     InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IAudioClient
    {
        [PreserveSig] int Initialize(int shareMode, int streamFlags, long bufferDuration,
                       long periodicity, IntPtr format, IntPtr audioSessionGuid);
        [PreserveSig] int GetBufferSize(out uint bufferFrames);
        [PreserveSig] int GetStreamLatency(out long latency);
        [PreserveSig] int GetCurrentPadding(out uint padding);
        [PreserveSig] int IsFormatSupported(int shareMode, IntPtr format, out IntPtr closestMatch);
        [PreserveSig] int GetMixFormat(out IntPtr format);
        [PreserveSig] int GetDevicePeriod(out long defaultPeriod, out long minPeriod);
        [PreserveSig] int Start();
        [PreserveSig] int Stop();
        [PreserveSig] int Reset();
        [PreserveSig] int SetEventHandle(IntPtr handle);
        [PreserveSig] int GetService(ref Guid iid, [MarshalAs(UnmanagedType.IUnknown)] out object service);
    }

    [ComImport, Guid("C8ADBD64-E71E-48a0-A4DE-185C395CD317"),
     InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IAudioCaptureClient
    {
        [PreserveSig] int GetBuffer(out IntPtr data, out uint frames, out uint flags,
                      out long devicePosition, out long qpcPosition);
        [PreserveSig] int ReleaseBuffer(uint frames);
        [PreserveSig] int GetNextPacketSize(out uint frames);
    }

    static class Native
    {
        [DllImport("ole32.dll")] public static extern int PropVariantClear(ref PropVariant pvar);
        public static readonly PropertyKey PKEY_FriendlyName = new PropertyKey
        { fmtid = new Guid("a45c254e-df1c-4efd-8020-67d146a850e0"), pid = 14 };
        // native format the device itself declares (the Sound panel's device format)
        public static readonly PropertyKey PKEY_DeviceFormat = new PropertyKey
        { fmtid = new Guid("f19f064d-082c-4e27-bc73-6882a1bb8e4c"), pid = 0 };
        public static readonly PropertyKey PKEY_OEMFormat = new PropertyKey
        { fmtid = new Guid("f19f064d-082c-4e27-bc73-6882a1bb8e4c"), pid = 3 };
    }

    // parsed WAVEFORMATEX(TENSIBLE) + the unmanaged copy we hand to Initialize
    class Fmt
    {
        public IntPtr Ptr; public int Channels; public int Rate; public int Bits;
        public int BlockAlign; public bool IsFloat;

        public static Fmt Parse(IntPtr fmtPtr)
        {
            Fmt f = new Fmt();
            f.Ptr        = fmtPtr;
            ushort tag   = (ushort)Marshal.ReadInt16(fmtPtr, 0);
            f.Channels   = Marshal.ReadInt16(fmtPtr, 2);
            f.Rate       = Marshal.ReadInt32(fmtPtr, 4);
            f.BlockAlign = Marshal.ReadInt16(fmtPtr, 12);
            f.Bits       = Marshal.ReadInt16(fmtPtr, 14);
            f.IsFloat    = (tag == 3);
            if (tag == 0xFFFE)
            {
                byte[] sub = new byte[16];
                Marshal.Copy(new IntPtr(fmtPtr.ToInt64() + 24), sub, 0, 16);
                f.IsFloat = (new Guid(sub) == new Guid("00000003-0000-0010-8000-00aa00389b71"));
            }
            return f;
        }

        public override string ToString()
        { return Rate + " Hz, " + Channels + " ch, " + Bits + "-bit " + (IsFloat ? "float" : "PCM"); }
    }

    // ---- WAV / RF64 writer -----------------------------------------------------
    // Layout: RIFF(4+4) WAVE(4) JUNK(8+28) fmt(8+16|18) [fact(8+4)] data(8+...)
    // The 28-byte JUNK placeholder becomes a ds64 chunk if the file passes 4 GB
    // (then RIFF->RF64 and the 32-bit sizes become 0xFFFFFFFF).
    class WavWriter
    {
        FileStream fs; BinaryWriter w;
        int channels; int rate; bool isFloat;
        long dataStart; long dataBytes;
        long factPos = -1;
        public string Path;

        public WavWriter(string path, int channels, int rate, bool isFloat)
        {
            this.channels = channels; this.rate = rate; this.isFloat = isFloat;
            Path = path;
            fs = new FileStream(path, FileMode.CreateNew, FileAccess.ReadWrite, FileShare.Read);
            w = new BinaryWriter(fs);
            int bits = isFloat ? 32 : 16;
            int blockAlign = channels * bits / 8;

            w.Write(0x46464952); // 'RIFF'
            w.Write(0);          // riff size (patched on Close)
            w.Write(0x45564157); // 'WAVE'

            w.Write(0x4B4E554A); // 'JUNK'  (ds64 placeholder)
            w.Write(28);
            w.Write(new byte[28]);

            w.Write(0x20746D66); // 'fmt '
            if (isFloat)
            {
                w.Write(18);
                w.Write((ushort)3); // IEEE_FLOAT
            }
            else
            {
                w.Write(16);
                w.Write((ushort)1); // PCM
            }
            w.Write((ushort)channels);
            w.Write(rate);
            w.Write(rate * blockAlign);
            w.Write((ushort)blockAlign);
            w.Write((ushort)bits);
            if (isFloat)
            {
                w.Write((ushort)0);  // cbSize
                w.Write(0x74636166); // 'fact'
                w.Write(4);
                factPos = fs.Position;
                w.Write(0);          // sample frames (patched on Close)
            }

            w.Write(0x61746164); // 'data'
            w.Write(0);          // data size (patched on Close)
            dataStart = fs.Position;
            dataBytes = 0;
        }

        public void Write(byte[] buf, int count) { w.Write(buf, 0, count); dataBytes += count; }

        // Keep the on-disk header valid at all times: called on every periodic flush
        // (not just Close), so a killed/crashed capture (USB yank, power cut) still
        // leaves a well-formed WAV whose sizes are at most ~1 s stale.
        void PatchHeader()
        {
            long endPos = fs.Position;
            long riffSize = (dataStart + dataBytes) - 8;
            int blockAlign = channels * (isFloat ? 4 : 2);
            long frames = dataBytes / blockAlign;
            if (riffSize <= uint.MaxValue)
            {
                fs.Seek(4, SeekOrigin.Begin);  w.Write((uint)riffSize);
                if (factPos >= 0) { fs.Seek(factPos, SeekOrigin.Begin); w.Write((uint)frames); }
                fs.Seek(dataStart - 4, SeekOrigin.Begin); w.Write((uint)dataBytes);
            }
            else
            {
                fs.Seek(0, SeekOrigin.Begin);  w.Write(0x34364652); // 'RF64'
                w.Write(unchecked((uint)0xFFFFFFFF));
                fs.Seek(12, SeekOrigin.Begin); w.Write(0x34367364); // JUNK -> 'ds64'
                w.Write(28);
                w.Write(riffSize); w.Write(dataBytes); w.Write(frames); w.Write(0);
                if (factPos >= 0) { fs.Seek(factPos, SeekOrigin.Begin); w.Write(unchecked((uint)0xFFFFFFFF)); }
                fs.Seek(dataStart - 4, SeekOrigin.Begin); w.Write(unchecked((uint)0xFFFFFFFF));
            }
            fs.Seek(endPos, SeekOrigin.Begin);
        }

        public void Flush() { w.Flush(); PatchHeader(); w.Flush(); }

        public void Close() { w.Flush(); PatchHeader(); w.Flush(); fs.Close(); }
    }

    // ---- capture engine --------------------------------------------------------
    public class Recorder
    {
        const int eCapture = 1, DEVICE_STATE_ACTIVE = 1, STGM_READ = 0, CLSCTX_ALL = 0x17;
        const int SHARED = 0, EXCLUSIVE = 1;
        const int E_NOT_ALIGNED = unchecked((int)0x88890019);   // AUDCLNT_E_BUFFER_SIZE_NOT_ALIGNED
        static Guid IID_IAudioClient = new Guid("1CB9AD4C-DBFA-4c32-B178-C2F568A703B2");
        static Guid IID_IAudioCaptureClient = new Guid("C8ADBD64-E71E-48a0-A4DE-185C395CD317");

        static void Check(int hr, string what)
        { if (hr != 0) throw new COMException(what + " failed (hr=0x" + hr.ToString("X8") + ")", hr); }

        static string FriendlyName(IMMDevice dev)
        {
            IPropertyStore store; Check(dev.OpenPropertyStore(STGM_READ, out store), "OpenPropertyStore");
            PropertyKey k = Native.PKEY_FriendlyName; PropVariant v;
            Check(store.GetValue(ref k, out v), "GetValue(FriendlyName)");
            string name = (v.vt == 31) ? Marshal.PtrToStringUni(v.p) : "(unknown)";
            Native.PropVariantClear(ref v);
            return name;
        }

        // device-declared native format (VT_BLOB WAVEFORMATEX), copied to CoTaskMem
        static IntPtr DeviceFormatPtr(IMMDevice dev)
        {
            IPropertyStore store; Check(dev.OpenPropertyStore(STGM_READ, out store), "OpenPropertyStore");
            foreach (PropertyKey key in new PropertyKey[] { Native.PKEY_DeviceFormat, Native.PKEY_OEMFormat })
            {
                PropertyKey k = key; PropVariant v;
                if (store.GetValue(ref k, out v) != 0) continue;
                if (v.vt == 65 /*VT_BLOB*/ && v.p2 != IntPtr.Zero)
                {
                    int cb = (int)(v.p.ToInt64() & 0xFFFFFFFF);
                    if (cb >= 16)
                    {
                        IntPtr copy = Marshal.AllocCoTaskMem(cb);
                        byte[] tmp = new byte[cb];
                        Marshal.Copy(v.p2, tmp, 0, cb);
                        Marshal.Copy(tmp, 0, copy, cb);
                        Native.PropVariantClear(ref v);
                        return copy;
                    }
                }
                Native.PropVariantClear(ref v);
            }
            return IntPtr.Zero;
        }

        static IAudioClient NewClient(IMMDevice dev)
        {
            object o; Guid iid = IID_IAudioClient;
            Check(dev.Activate(ref iid, CLSCTX_ALL, IntPtr.Zero, out o), "Activate(IAudioClient)");
            return (IAudioClient)o;
        }

        public static string[] ListDevices()
        {
            IMMDeviceEnumerator en = (IMMDeviceEnumerator)(object)new MMDeviceEnumeratorCom();
            IMMDeviceCollection coll; Check(en.EnumAudioEndpoints(eCapture, DEVICE_STATE_ACTIVE, out coll), "EnumAudioEndpoints");
            uint n; Check(coll.GetCount(out n), "GetCount");
            string[] names = new string[n];
            for (uint i = 0; i < n; i++)
            {
                IMMDevice d; Check(coll.Item(i, out d), "Item");
                string line = FriendlyName(d);
                try
                {
                    IntPtr df = DeviceFormatPtr(d);
                    if (df != IntPtr.Zero) { line += "  [native: " + Fmt.Parse(df) + "]"; Marshal.FreeCoTaskMem(df); }
                    IntPtr mf; if (NewClient(d).GetMixFormat(out mf) == 0)
                    { line += "  [shared: " + Fmt.Parse(mf) + "]"; Marshal.FreeCoTaskMem(mf); }
                }
                catch { }
                names[i] = line;
            }
            return names;
        }

        // Resolution order: (1) EXACT friendly-name match (case-insensitive) - required
        // when two mics share a substring, e.g. "Microphone (UltraMic384K_EVO 16bit r0)"
        // vs "Microphone (2- UltraMic384K_EVO 16bit r0)"; (2) unique substring match.
        // Never picks silently among multiple hits - a wrong pick would record the
        // wrong mic into a folder after a reboot.
        static IMMDevice FindDevice(string match)
        {
            IMMDeviceEnumerator en = (IMMDeviceEnumerator)(object)new MMDeviceEnumeratorCom();
            IMMDeviceCollection coll; Check(en.EnumAudioEndpoints(eCapture, DEVICE_STATE_ACTIVE, out coll), "EnumAudioEndpoints");
            uint n; Check(coll.GetCount(out n), "GetCount");
            IMMDevice found = null; string foundName = null; int hits = 0;
            IMMDevice exact = null; string exactName = null; int exactHits = 0;
            for (uint i = 0; i < n; i++)
            {
                IMMDevice d; Check(coll.Item(i, out d), "Item");
                string name = FriendlyName(d);
                if (name.Equals(match, StringComparison.OrdinalIgnoreCase))
                { exactHits++; exact = d; exactName = name; }
                if (name.IndexOf(match, StringComparison.OrdinalIgnoreCase) >= 0)
                { hits++; found = d; foundName = name; }
            }
            if (exactHits == 1) { Console.WriteLine("device (exact): " + exactName); return exact; }
            if (exactHits > 1) throw new Exception("'" + match + "' exactly matches " + exactHits + " capture devices");
            if (hits == 0) throw new Exception("no active capture device matches '" + match + "'");
            if (hits > 1) throw new Exception("'" + match + "' matches " + hits + " capture devices; use the EXACT full name from -ListDevices");
            Console.WriteLine("device: " + foundName);
            return found;
        }

        static DateTime NextBoundary(DateTime now, int segmentSeconds)
        {
            DateTime midnight = now.Date;
            int sec = (int)(now - midnight).TotalSeconds;
            int k = (sec / segmentSeconds) + 1;
            return midnight.AddSeconds((long)k * segmentSeconds);
        }

        static string OpenName(string outDir, string prefix, DateTime t)
        { return System.IO.Path.Combine(outDir, prefix + "_" + t.ToString("yyyy-MM-dd_HH-mm-ss") + ".wav"); }

        static void FinalizeSegment(WavWriter ww, DateTime endTime)
        {
            ww.Close();
            string bn = System.IO.Path.GetFileNameWithoutExtension(ww.Path);
            string dir = System.IO.Path.GetDirectoryName(ww.Path);
            string dst = System.IO.Path.Combine(dir, bn + "_to_" + endTime.ToString("HH-mm-ss") + ".wav");
            try { File.Move(ww.Path, dst); Console.WriteLine("finalized " + System.IO.Path.GetFileName(dst)); }
            catch (Exception ex) { Console.WriteLine("WARN rename failed: " + ex.Message); }
        }

        // plain 16-byte WAVEFORMATEX PCM (some drivers reject EXTENSIBLE in exclusive mode)
        static IntPtr PlainPcmFormat(int rate, int channels, int bits)
        {
            int blockAlign = channels * bits / 8;
            IntPtr p = Marshal.AllocCoTaskMem(18);
            Marshal.WriteInt16(p, 0, (short)1);                    // WAVE_FORMAT_PCM
            Marshal.WriteInt16(p, 2, (short)channels);
            Marshal.WriteInt32(p, 4, rate);
            Marshal.WriteInt32(p, 8, rate * blockAlign);
            Marshal.WriteInt16(p, 12, (short)blockAlign);
            Marshal.WriteInt16(p, 14, (short)bits);
            Marshal.WriteInt16(p, 16, (short)0);                   // cbSize
            return p;
        }

        // Initialize an exclusive-mode client, handling the buffer-alignment dance.
        // Tries the device-declared format blob first, then a plain PCM WAVEFORMATEX.
        // Returns null (with diagnostics) if exclusive mode is unavailable.
        static IAudioClient InitExclusive(IMMDevice dev, IntPtr devFmtPtr, Fmt fmt)
        {
            IntPtr[] formats = new IntPtr[] { devFmtPtr, PlainPcmFormat(fmt.Rate, fmt.Channels, fmt.Bits) };
            string[] fmtNames = new string[] { "device blob", "plain PCM" };
            for (int fi = 0; fi < formats.Length; fi++)
            {
                // driver's own opinion first (purely diagnostic)
                IAudioClient probe = NewClient(dev);
                IntPtr closest;
                int sup = probe.IsFormatSupported(EXCLUSIVE, formats[fi], out closest);
                Console.WriteLine("IsFormatSupported(exclusive, " + fmtNames[fi] + ") hr=0x" + sup.ToString("X8"));
                Marshal.ReleaseComObject(probe);

                foreach (long dur in new long[] { 10000000, 5000000, 2000000, 1000000 }) // 1s .. 100ms
                {
                    IAudioClient c = NewClient(dev);
                    int hr = c.Initialize(EXCLUSIVE, 0, dur, 0, formats[fi], IntPtr.Zero);
                    if (hr == 0) return c;
                    if (hr == E_NOT_ALIGNED)
                    {
                        uint frames;
                        if (c.GetBufferSize(out frames) == 0)
                        {
                            long aligned = (long)Math.Round(10000000.0 * frames / fmt.Rate);
                            Marshal.ReleaseComObject(c);
                            c = NewClient(dev);
                            hr = c.Initialize(EXCLUSIVE, 0, aligned, 0, formats[fi], IntPtr.Zero);
                            if (hr == 0) return c;
                        }
                    }
                    Marshal.ReleaseComObject(c);
                    Console.WriteLine("exclusive init (" + fmtNames[fi] + ", buffer " + (dur / 10000) +
                                      " ms) hr=0x" + hr.ToString("X8"));
                    // no point retrying buffer sizes for "format not supported"-class errors
                    if (hr != E_NOT_ALIGNED && hr != unchecked((int)0x88890016)) break;
                }
            }
            return null;
        }

        // returns 0 on clean stop
        public static int Record(string deviceMatch, string outDir, string prefix,
                                 int segmentSeconds, int maxSeconds, bool storeFloat, string mode)
        {
            IMMDevice dev = FindDevice(deviceMatch);
            IAudioClient client = null;
            Fmt fmt = null;

            if (mode == "exclusive" || mode == "auto")
            {
                IntPtr devFmt = DeviceFormatPtr(dev);
                if (devFmt != IntPtr.Zero)
                {
                    fmt = Fmt.Parse(devFmt);
                    Console.WriteLine("device native format: " + fmt);
                    client = InitExclusive(dev, devFmt, fmt);
                    if (client == null)
                    {
                        Console.WriteLine("WARN: exclusive mode unavailable" +
                            (mode == "auto" ? "; falling back to shared" : ""));
                        fmt = null;
                    }
                    else Console.WriteLine("capture mode: EXCLUSIVE (native format, engine bypassed)");
                }
                else Console.WriteLine("WARN: device native format property not readable");
                if (client == null && mode == "exclusive") throw new Exception("exclusive-mode init failed");
            }

            if (client == null)   // shared (requested, or auto-fallback)
            {
                client = NewClient(dev);
                IntPtr mixPtr; Check(client.GetMixFormat(out mixPtr), "GetMixFormat");
                fmt = Fmt.Parse(mixPtr);
                Console.WriteLine("capture mode: SHARED (engine mix format: " + fmt + ")");
                if (fmt.Rate < 192000)
                    Console.WriteLine("WARN: shared-mode rate is only " + fmt.Rate +
                        " Hz - ultrasound is being discarded. Raise the endpoint Default Format" +
                        " in the Sound control panel, or use exclusive mode.");
                Check(client.Initialize(SHARED, 0, 10000000, 0, mixPtr, IntPtr.Zero), "Initialize(shared)");
            }

            if (!fmt.IsFloat && fmt.Bits != 16)
                throw new Exception("unsupported stream format (" + fmt.Bits + "-bit PCM)");

            uint bufFrames; Check(client.GetBufferSize(out bufFrames), "GetBufferSize");
            object oc; Guid iidCap = IID_IAudioCaptureClient;
            Check(client.GetService(ref iidCap, out oc), "GetService(IAudioCaptureClient)");
            IAudioCaptureClient cap = (IAudioCaptureClient)oc;

            bool outFloat = storeFloat;
            int outBlockAlign = fmt.Channels * (outFloat ? 4 : 2);
            Console.WriteLine("storing: " + fmt.Rate + " Hz, " + fmt.Channels + " ch, " +
                (outFloat ? "float32" : "int16") + " (~" +
                ((long)fmt.Rate * outBlockAlign * 3600 / (1024L * 1024 * 1024)) + " GB/hour)");

            byte[] raw = new byte[bufFrames * fmt.BlockAlign];
            byte[] outBuf = new byte[bufFrames * outBlockAlign];

            DateTime start = DateTime.Now;
            DateTime boundary = NextBoundary(start, segmentSeconds);
            WavWriter ww = new WavWriter(OpenName(outDir, prefix, start), fmt.Channels, fmt.Rate, outFloat);
            Console.WriteLine("opened " + System.IO.Path.GetFileName(ww.Path));

            Check(client.Start(), "Start");
            long lastFlush = Environment.TickCount;
            try
            {
                while (true)
                {
                    Thread.Sleep(20);
                    uint pkt;
                    Check(cap.GetNextPacketSize(out pkt), "GetNextPacketSize");
                    while (pkt > 0)
                    {
                        IntPtr data; uint frames; uint flags; long dp, qp;
                        Check(cap.GetBuffer(out data, out frames, out flags, out dp, out qp), "GetBuffer");
                        int nBytes = (int)frames * fmt.BlockAlign;
                        if (nBytes > raw.Length) { raw = new byte[nBytes]; outBuf = new byte[(int)frames * outBlockAlign]; }
                        if ((flags & 2) != 0) Array.Clear(raw, 0, nBytes);       // SILENT flag
                        else Marshal.Copy(data, raw, 0, nBytes);
                        Check(cap.ReleaseBuffer(frames), "ReleaseBuffer");

                        int nSamp = (int)frames * fmt.Channels;
                        if (fmt.IsFloat == outFloat)
                            ww.Write(raw, nBytes);                                // passthrough
                        else if (fmt.IsFloat)                                     // float32 -> int16
                        {
                            for (int i = 0; i < nSamp; i++)
                            {
                                float f = BitConverter.ToSingle(raw, i * 4);
                                int s = (int)Math.Round(f * 32767f);
                                if (s > 32767) s = 32767; else if (s < -32768) s = -32768;
                                outBuf[i * 2] = (byte)(s & 0xFF);
                                outBuf[i * 2 + 1] = (byte)((s >> 8) & 0xFF);
                            }
                            ww.Write(outBuf, nSamp * 2);
                        }
                        else                                                      // int16 -> float32
                        {
                            for (int i = 0; i < nSamp; i++)
                            {
                                short s = (short)(raw[i * 2] | (raw[i * 2 + 1] << 8));
                                byte[] fb = BitConverter.GetBytes(s / 32768f);
                                outBuf[i * 4] = fb[0]; outBuf[i * 4 + 1] = fb[1];
                                outBuf[i * 4 + 2] = fb[2]; outBuf[i * 4 + 3] = fb[3];
                            }
                            ww.Write(outBuf, nSamp * 4);
                        }

                        Check(cap.GetNextPacketSize(out pkt), "GetNextPacketSize");
                    }

                    if (Environment.TickCount - lastFlush > 1000) { ww.Flush(); lastFlush = Environment.TickCount; }

                    DateTime now = DateTime.Now;
                    if (maxSeconds > 0 && (now - start).TotalSeconds >= maxSeconds)
                    {
                        client.Stop(); FinalizeSegment(ww, now);
                        Console.WriteLine("test clip done (" + maxSeconds + " s)");
                        return 0;
                    }
                    if (now >= boundary)
                    {
                        FinalizeSegment(ww, now);
                        ww = new WavWriter(OpenName(outDir, prefix, now), fmt.Channels, fmt.Rate, outFloat);
                        Console.WriteLine("opened " + System.IO.Path.GetFileName(ww.Path));
                        boundary = NextBoundary(now, segmentSeconds);
                    }
                }
            }
            finally
            {
                try { client.Stop(); } catch { }
            }
        }
    }
}
'@

if ($ListDevices) {
    Write-Host 'Active capture endpoints:' -ForegroundColor Cyan
    [UltraMicCap.Recorder]::ListDevices() | ForEach-Object { Write-Host "  $_" }
    exit 0
}

if (-not $OutDir) { Write-Error 'OutDir is required'; exit 2 }

# one capture per Prefix (the supervisor treats exit 3 as "orphan still running")
$mtx = New-Object System.Threading.Mutex($false, ("Global\FieldUltraMicCapture_{0}" -f $Prefix))
if (-not $mtx.WaitOne(0)) { Write-Host "capture for $Prefix already running; exiting."; exit 3 }

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
try {
    $rc = [UltraMicCap.Recorder]::Record($Device, $OutDir, $Prefix, $SegmentSeconds, $Seconds, ($StoreFormat -eq 'float32'), $Mode)
    exit $rc
} catch {
    Write-Host ("FATAL: {0}" -f $_.Exception.Message) -ForegroundColor Red
    exit 2
}
