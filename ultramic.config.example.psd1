@{
    # ==========================================================================
    # UltraMic384K audio recorder config.
    # Copy this file to  E:\ultramic_record\ultramic.config.psd1  and fill it in.
    # The real file is kept OUT of git (the *.config.psd1 rule in .gitignore) by
    # policy, like every other recorder config.
    # ==========================================================================

    # Dedicated root, kept SEPARATE from E:\Reolink_record / E:\thermal_record so
    # the video QC/copy/delete tooling never sees these audio files. Files land at
    #   <Root>\<Name>\<Name>_<start>_to_<end>.wav
    Root = 'E:\ultramic_record'

    # --- capture ---------------------------------------------------------------
    # Capture is WASAPI (no ffmpeg; see README_ultramic.md for why). In exclusive
    # mode the device is opened at ITS OWN native format - for the UltraMic384K_EVO
    # that is 384000 Hz / 1 ch / 16-bit, measured on this PC 2026-07-17 - so there
    # is no sample-rate setting here; the device declares it.
    #   auto      = exclusive first, shared as a loudly-warned fallback (default)
    #   exclusive = native format, engine bypassed, mic locked to the recorder
    #   shared    = Windows default format - on this PC only 48 kHz; ultrasound
    #               would be silently discarded. Not for production.
    Mode = 'auto'

    # int16 (default) = matches the mic's 16-bit ADC; ~2.76 GB/hour at 384 kHz.
    # float32 = 2x the bytes for no extra information with this mic; segments
    # over 4 GB are written as RF64 automatically.
    StoreFormat = 'int16'

    # --- segmentation & robustness ---------------------------------------------
    SegmentSeconds = 3600   # hourly files, split on the clock hour (matches video)
    StallSeconds   = 240    # no file growth for this long -> restart that mic

    # --- retention (OFF by policy: nothing here deletes footage automatically) ---
    RetentionDays = 0       # 0 = keep forever (the sanctioned delete path is copy->delete)
    MinFreeGB     = 0       # 0 = disk-guard disabled (never auto-deletes to free space)

    # --- the mic(s) -------------------------------------------------------------
    # Name  : short unique label -> folder + filename prefix (keep it space-free).
    # Device: the EXACT WASAPI endpoint friendly name from  -ListDevices  (preferred;
    #         exact match wins even when two mics share a substring). A unique
    #         substring also works while only one mic matches it. A second identical
    #         UltraMic enumerates as "Microphone (2- UltraMic384K_EVO 16bit r0)" -
    #         always use exact full names once two mics are connected.
    # Adding a mic to a LIVE recorder: edit this list, then restart ONLY the
    # supervisor process (the running capture children keep recording and are
    # adopted via their mutexes; see README_ultramic.md "Adding a second mic").
    Streams = @(
        @{ Name = 'MIC01'; Device = 'Microphone (UltraMic384K_EVO 16bit r0)' }
        # @{ Name = 'MIC02'; Device = 'PASTE-EXACT-NAME-FROM-ListDevices' }
    )
}
