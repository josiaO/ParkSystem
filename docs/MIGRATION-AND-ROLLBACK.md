# Desktop/video update and rollback

Close SmartPark clients and stop the installed SmartPark services before replacing application files. Back up the installation and its data/configuration first. Keep the existing tested vendor DLL family, model pack and Python wheel bundle together. Do not erase the parking database or reset camera settings for this update.

Use the refreshed `dist/SmartParkEdge-Install` folder and its installer. Start **SmartPark Edge** for the desktop operator UI. The web shortcut remains available. The desktop launcher starts/reuses the background service rather than hosting a second service in the UI for normal operation.

After installation run `Run-StartupCheck.bat`, then `Run-FieldAcceptanceTest.bat` while vehicles pass. Inspect both video freshness and recognition results; a plate result alone is not proof of a functioning video stream. For a longer observation window the supplied `tools/field_acceptance_test.py` supports `--minutes 60`. Review its output and the Windows service logs before declaring the update ready for unattended operation.

If problems appear, stop services and clients and restore the previous application installation with its matched dependencies and configuration. Preserve new parking transactions; do not blindly overwrite a database that has accepted new vehicles. This change introduces no database migration and does not alter gate pulse settings.
