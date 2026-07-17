# config/auto_publish

TRIAL MODE FLAG. `true` = scheduled runs publish WITHOUT the human GitHub
approval gate (validator hard-fail is then the only gate). `false` = normal
behaviour, human approval required.

Enabled 2026-07-18 at Micah's explicit request as a trial (he is currently
the only subscriber on every platform). To end the trial and restore the
human gate, change this file's contents to `false` and commit — one line,
nothing else to touch.
