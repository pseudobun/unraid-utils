import csv
import os
import argparse
import PTN
import time
import shutil


def parse_args():
    parser = argparse.ArgumentParser(prog="Tdarr xref",
                                     description='Read transcoded media from Tdarr CSV export and remove the original files.')
    parser.add_argument('--file', '-f',
                        required=True,
                        help='Tdarr exported CSV file path')
    parser.add_argument('--dir', '-d',
                        required=True,
                        help='Original downloads folder path')
    parser.add_argument('--force',
                        help="If this flag is set, the script will delete all found original files, even those it may skip during the process",
                        action='store_true')
    return parser.parse_args()


def yes_or_no(question):
    reply = str(input(question + ' (y/n): ')).lower().strip()
    if reply == "":
        return True
    if reply[0] == 'y':
        return True
    if reply[0] == 'n':
        return False
    else:
        return yes_or_no("Uhhhh... please enter ")


def get_size(start_path='.'):
    if start_path.endswith(".mkv") or start_path.endswith(".mp4"):
        return round(os.path.getsize(start_path)/(1024*1024*1024), 2)
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(start_path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            if not os.path.islink(fp):
                total_size += os.path.getsize(fp)

    return round(total_size/(1024*1024*1024), 2)


def delete_file(file, interactive=False):
    if not interactive and os.path.isfile(file):
        os.remove(file)
        return True

    if not interactive:
        shutil.rmtree(file)
        return True

    if os.path.isfile(file) and yes_or_no(f"Delete {file}"):
        os.remove(file)
        return True

    if os.path.isdir(file) and yes_or_no(f"Delete folder {file}"):
        shutil.rmtree(file)
        return True

    return False


def main(csv_file, root, force=False):
    if not root.endswith("/"):
        root = root + "/"
    print(f"Cross referencing files from {csv_file} with files from {root}")
    print(f"Force set to {force}\n")
    # Open the CSV file
    with open(csv_file, "r") as csv_file_read:
        tdarr_export = csv.DictReader(csv_file_read)
        to_delete = []
        saved_size = 0
        for row in tdarr_export:
            if row["newSize"] == '0':
                continue
            torrent_path = row["_id"]
            torrent_name = os.path.basename(os.path.normpath(torrent_path))
            torrent_info = PTN.parse(torrent_name)
            try:
                for element in os.listdir(root):
                    element_info = PTN.parse(element)
                    if element_info["title"] == torrent_info["title"] and element_info["year"] == torrent_info["year"]:
                        print(f"Staged for delete: {root + element} of size {get_size(root + element)} GB")
                        to_delete.append(os.path.join(root, element))
                        saved_size += get_size(root + element)
            except KeyError:
                print(f"Error for torrent {torrent_info['title']}")
        if saved_size > 1000:
            saved_size = f"{round(saved_size/1000, 2)} TB"
        else:
            saved_size = f"{round(saved_size, 2)} GB"
        skipped = []
        deleted = 0
        if force or yes_or_no(f"Folders and files above will be deleted saving collectively {saved_size}. Continue?"):
            print("\nDeleting files...")
            for file in to_delete:
                try:
                    if os.path.getctime(file) > time.time() - 604800:
                        skipped.append(file)
                        continue
                    if delete_file(file):
                        print(f"Deleted {file}")
                        deleted += 1
                except OSError as e:
                    print("Error: %s : %s" % (file, e.strerror))
            print(f"{deleted} files deleted\n")

            if not skipped:
                exit(0)

            deleted = 0
            # Handle skipped files if forced
            if force:
                print("Force deleting skipped files...")
                for file in skipped:
                    try:
                        if delete_file(file):
                            print(f"Deleted {file}")
                            deleted += 1
                    except OSError as e:
                        print("Error: %s : %s" % (file, e.strerror))
                print(f"{deleted} skipped files deleted\n")
                exit(0)

            # Handle skipped files gracefully
            for file in skipped:
                print(f"Skipped {file}, created/modified on {time.strftime('%d %B %Y %H:%M:%S', time.localtime(os.path.getctime(file)))}")
            deleted = 0
            if yes_or_no("Interactively delete skipped files?"):
                for file in skipped:
                    try:
                        if delete_file(file, True):
                            print(f"Deleted {file}")
                            deleted += 1
                    except OSError as e:
                        print("Error: %s : %s" % (file, e.strerror))
                print(f"{deleted} skipped files deleted\n")
                exit(0)

            if yes_or_no("Delete all skipped files?") and yes_or_no("Are you sure?"):
                for file in skipped:
                    try:
                        if delete_file(file, False):
                            print(f"Deleted {file}")
                            deleted += 1
                    except OSError as e:
                        print("Error: %s : %s" % (file, e.strerror))
                print(f"{deleted} skipped files deleted\n")
            exit(0)

        else:
            print("Nothing deleted")
            exit(0)


if __name__ == "__main__":
    args = parse_args()
    main(args.file, args.dir, args.force)
