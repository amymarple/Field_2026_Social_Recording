@{
    # ============================================================================
    # Overexposure / near-black QC config.
    # Copy this file to  E:\recording_qc\overexposure.config.psd1  and fill it in.
    # The real file holds the Slack token and is kept OUT of git (the *.config.psd1
    # rule in reolink_record/.gitignore). NEVER commit the filled-in version.
    # ============================================================================

    # --- Slack (AYAlab workspace) ---------------------------------------------
    # A bot token (xoxb-...) with scopes:  chat:write, im:write  (and files:write
    # only if you enable UploadImage below). Create it at https://api.slack.com/apps
    # (Create App -> OAuth & Permissions -> add scopes -> Install -> copy Bot token),
    # then invite the bot to the team channel.
    SlackBotToken = 'xoxb-REPLACE-ME'

    # Where alerts go. Mix of:
    #   - a CHANNEL id  (Cxxxxxxxx)  -> posted to the team channel
    #   - a USER id     (Uxxxxxxxx)  -> resolved via conversations.open to a DM
    # Get ids from Slack: click a channel/profile -> "Copy member ID" / channel
    # details -> Channel ID. Hongyu's user id is the DM destination.
    SlackChannels = @(
        'C0XXXXXXXXX',     # <- team channel id
        'U0XXXXXXXXX'      # <- Hongyu Chang's user id (becomes a DM)
    )

    # --- detection thresholds (tune against the logs in E:\recording_qc\overexposure) ---
    SatLuma         = 250     # a pixel with luma >= this is "saturated/clipped"
    DarkLuma        = 16      # a pixel with luma <= this is "black"
    SatRatioThresh  = 0.20    # OVEREXPOSED if >= this fraction of pixels is saturated...
    MeanHighThresh  = 235     # ...or whole-frame mean luma (0-255) >= this
    DarkRatioThresh = 0.98    # NEAR_BLACK if >= this fraction of pixels is black...
    MeanLowThresh   = 12      # ...or mean luma <= this

    # --- alerting behaviour ----------------------------------------------------
    RealertHours = 6          # while a channel stays flagged, re-alert at most this often
    SendRecovery = $true      # send a one-line "back to normal" note when it clears
    UploadImage  = $false     # best-effort attach the offending frame (needs files:write)
}
