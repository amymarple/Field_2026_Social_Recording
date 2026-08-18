@{
    # ==========================================================================
    # Interactive GUI recorder config.
    # OPTIONAL: the GUI runs with sensible defaults without this file.
    # To customize, copy to  gui_recorder.config.psd1  (same folder as the
    # script; that name is gitignored because custom camera URLs hold creds).
    # ==========================================================================

    # Where GUI recordings land: <OutputRoot>\<CameraName>\<Name>_<start>.mp4
    # Kept SEPARATE from E:\Reolink_record so QC/copy/delete tooling for the
    # production recordings never sees these files.
    OutputRoot = 'E:\gui_record'

    # '' = auto (E:\Reolink_record\bin\ffmpeg.exe, then PATH)
    FfmpegPath = ''

    # Also list the production NVR channels (CH01-06) and extra cams (CH07-08).
    # They normally show as blue SERVICE rows (the SYSTEM task records them and
    # the GUI leaves them alone); useful as a manual fallback when that task is
    # stopped.
    ImportProductionChannels = $true
    ProductionConfig         = 'E:\Reolink_record\recorder.config.psd1'   # CH01-06 via NVR bridge
    ExtraCamConfig           = 'E:\Reolink_record\extra_cam.config.psd1'  # CH07/08 direct-IP
    ThermalConfig            = 'E:\thermal_record\thermal.config.psd1'    # 108/109 direct-IP (4 streams)

    # Additional security cameras (any RTSP source). Name must be unique.
    Cameras = @(
        # @{ Name = 'SEC01'; Url = 'rtsp://user:password@192.168.1.210:554/stream1' }
        # @{ Name = 'SEC02'; Url = 'rtsp://user:password@192.168.1.211:554/cam/realmonitor?channel=1&subtype=0' }
    )

    SegmentSeconds = 3600      # hourly files, split on the clock hour
    StallSeconds   = 60        # no file growth for this long -> STALLED (auto-restart)
}
