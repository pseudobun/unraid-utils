import shutil
import PTN
import sys
import os
import uuid
import datetime
import re


def yes_no(question):
    reply = str(input(question + ' (y/n): ')).lower().strip()
    if reply == "":
        return True
    if reply[0] == 'y':
        return True
    if reply[0] == 'n':
        return False
    else:
        return yes_no("Uhhhh... please enter ")


def detect_season(torrent):
    if not "excess" in torrent:
        return torrent
    season_indices = [i for i, item in enumerate(torrent["excess"]) if re.search('S[0-9]+$', item)]
    if "excess" in torrent and season_indices:
        season = torrent["excess"][season_indices[0]]
        if len(season) > 3:
            return torrent
        else:
            torrent["season"] = int((torrent["excess"][season_indices[0]])[1:].strip("0"))
            return torrent
    if "excess" in torrent and "season" in torrent["excess"]:
        torrent["season"] = int(torrent["excess"][torrent["excess"].index("season")+1])
    if "excess" in torrent and "Season" in torrent["excess"]:
        torrent["season"] = int(torrent["excess"][torrent["excess"].index("Season")+1])
    if "excess" in torrent and "SEASON" in torrent["excess"]:
        torrent["season"] = int(torrent["excess"][torrent["excess"].index("SEASON")+1])


    return torrent


def check_dupes(path, force=False, dry=False):
    files = [(f, uuid.uuid4(), os.path.getmtime(path + "/" + f)) for f in os.listdir(path)]
    print("Detecting dupes: ")
    delete_count = 0
    found_count = 0
    for torrent_file in files:
        torrent = PTN.parse(torrent_file[0])
        includes_season = True if (
                ("excess" in torrent) and ("Season" in torrent or "season" in torrent["excess"] or "Season" in
                                           torrent["excess"] or "SEASON" in torrent["excess"])) else False

        torrent = detect_season(torrent)

        show = True if "season" in torrent or includes_season else False

        for duplicate_file in files:
            dupe = PTN.parse(duplicate_file[0])
            dupe = detect_season(dupe)
            # checks if uuids are the same
            if duplicate_file[1] != torrent_file[1] and dupe["title"] == torrent["title"]:
                includes_episode = True if "episode" in dupe and "episode" in torrent else False
                if show and includes_episode and dupe["episode"] != torrent["episode"]:
                    continue 
                if "season" in dupe and "season" in torrent and dupe["season"] != torrent["season"]:
                    continue
                if "year" in torrent and "year" in dupe and torrent["year"] != dupe["year"]:
                    continue

                date_m_torrent = datetime.datetime.fromtimestamp(torrent_file[2])
                date_m_dupe = datetime.datetime.fromtimestamp(duplicate_file[2])
                # check which file is newer
                if date_m_torrent > date_m_dupe:
                    to_remove = duplicate_file
                    remaining = torrent_file
                else:
                    to_remove = torrent_file
                    remaining = duplicate_file
                    torrent_file = duplicate_file

                if datetime.datetime.fromtimestamp(to_remove[2]) < datetime.datetime.now() - datetime.timedelta(
                        days=10):
                    date_local_delete = datetime.datetime.fromtimestamp(to_remove[2]).strftime('%d-%m-%Y at %H:%M:%S')
                    date_local_keep = datetime.datetime.fromtimestamp(remaining[2]).strftime('%d-%m-%Y at %H:%M:%S')
                    question = "DELETE: " + to_remove[0] + ", created on " + str(date_local_delete) + "\nKEEP: " + \
                               remaining[0] + ", created on " + str(date_local_keep)
                    found_count += 1
                    if dry:
                        print(question)
                        continue
                    if force or yes_no(question + "\nAgree?"):
                        absolute_path = path + "/" + to_remove[0]
                        directory = False
                        if os.path.isdir(absolute_path):
                            directory = True

                        files.remove(to_remove)
                        try:
                            if directory:
                                # remove directory
                                shutil.rmtree(absolute_path)
                            else:
                                # remove file
                                os.remove(absolute_path)
                        except:
                            print("Error while deleting file/directory.")
                        print("Removed: " + absolute_path)
                        delete_count += 1
    print("Eligible duplicates found: " + str(found_count))
    print("Duplicates deleted: " + str(delete_count))


if __name__ == '__main__':
    force = False
    dry = False
    if len(sys.argv) >= 3 and sys.argv[2] == "force":
        yes_no("Forcing deletion will not ask for your confirmation. Are you sure you want to continue?")
        force = True
    elif len(sys.argv) >= 3 and sys.argv[2] == "dry":
        dry = True
    check_dupes(sys.argv[1], force=force, dry=dry)
