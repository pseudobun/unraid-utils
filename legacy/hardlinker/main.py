import PTN
import os
import sys


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


def main():
    counter = 0
    # get first passed argument
    path = os.path.abspath(os.path.expanduser(sys.argv[1]))
    # get second passed argument as destination path
    dest = os.path.abspath(os.path.expanduser(sys.argv[2]))
    # create hardlinks of folder from path to destination
    for root, dirs, files in os.walk(path):
        for file in files:
            if file.endswith(".mkv") or file.endswith(".m4v") or file.endswith(".mp4"):
                counter += 1
                file_path = os.path.join(root, file)
                info = PTN.parse(file_path)
                final_dest = os.path.join(dest + "/Season " + str(info["season"]))
                if yes_or_no(file_path + " -> " + os.path.join(final_dest, file)):
                    try:
                        # create folder if not exists
                        if not os.path.exists(os.path.join(final_dest)):
                            os.makedirs(os.path.join(final_dest))
                        os.link(file_path, os.path.join(final_dest, file))
                        print("Link created")
                    except FileExistsError:
                        if yes_or_no("File already exists, overwrite?"):
                            os.remove(os.path.join(final_dest, file))
                            os.link(file_path, os.path.join(final_dest, file))
                            print("Link created")
                        else:
                            print("Skipping file: " + file)
                    except Exception as e:
                        print("Error: " + str(e))

    print("Hard links created: " + str(counter))


if __name__ == "__main__":
    main()
