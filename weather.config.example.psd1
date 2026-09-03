@{
    # Local weather listener config. Copy to  D:\weather_data\weather.config.psd1
    # (optional - weather_listener.ps1 runs with these same defaults if the file is
    # absent). No secrets live here; the file is kept out of git only by the blanket
    # *.config.psd1 rule so it can carry site-specific values.

    # Where daily CSVs (AWN export schema), raw\*.jsonl, state and logs go.
    Root         = 'D:\weather_data\local'

    # TCP port the console posts to. The installer opens it for the local subnet.
    Port         = 8085

    # Path the console is configured with (Ecowitt "Customized upload"). The
    # listener also accepts /weatherstation/ (Wunderground protocol) and / .
    Path         = '/data/report/'

    # Filename prefix - keep it equal to the station id used by the cloud exports
    # (AWN-<console MAC>) so local and cloud files sort together.
    StationLabel = 'AWN-F8B3B78DEAC9'

    # The router-LAN adapter the console can reach. The installer opens the port on
    # THIS interface only, so the camera and WISER jacks (which share the same
    # 192.168.1.0/24 numbering) never expose it.
    LanInterfaceAlias = 'Ethernet'
}
