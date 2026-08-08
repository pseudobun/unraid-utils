# Torrent downloads duplicate checker

This script takes a directory as a parameter and checks for duplicate torrents in the directory.

To run this script:

e.g. your downloads folder is located in `/mnt/user/plex/downloads`

1. First of all install the required packages with `pip install -r requirements.txt`.
2. Run `python main.py /mnt/user/plex/downloads`.
3. The script will indicate the torrent to remove. Type `y` and hit enter, or just hit enter to accept the deletion or type `n` and hit enter to reject. 
4. That's pretty much it.

Extra cookie: If you live in a pile of duplicates and don't want to click `y` or enter for every found duplicate and you trust me with your life (I wouldn't), just run:
`python3 main.py /mnt/user/plex/downloads force`