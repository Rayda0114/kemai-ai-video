Source: https://github.com/harry0703/MoneyPrinterTurbo
Commit: 5ac2b5d979adba31f6489ba50f94f4771427549f
License: MIT, preserved in LICENSE.
Vendored app/ only; original fonts, media and secrets are excluded.
KEMAI change: VideoAspect resolutions changed to 720p to bound free-host memory.
Only voice, subtitle timing, schema and their utilities are used. KEMAI's FFmpeg compositor handles images and final encoding within the free CPU budget. Original public API and configuration UI are not exposed.
