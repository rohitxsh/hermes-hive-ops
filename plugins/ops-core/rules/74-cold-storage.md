---
profiles: *
---
- Cold storage on an external disk: when this machine has a USB vault mounted at `/mnt/ext-backup` (check with `mountpoint -q /mnt/ext-backup`), put large data you rarely read in `/mnt/ext-backup/cold/<your profile>/`: finished raw downloads, old run artifacts, datasets you may need again. Add a short README there saying what the files are and where they came from. The disk is slow, not encrypted and not backed up, so never put secrets, tokens, credentials or personal data there, and keep anything you use daily on the system disk. If the disk isn't mounted, leave the data where it is and say so. Write only inside `cold/`: backups and mirrors live in the disk's other folders.
