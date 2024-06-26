import json
from itertools import zip_longest

import requests
import tqdm
import urllib3
import os
import os.path
import sqlite3
import subprocess
from concurrent.futures import ThreadPoolExecutor

from requests.exceptions import ChunkedEncodingError
from urllib3.exceptions import ProtocolError

urllib3.disable_warnings()

json_file_path='/Library/Application Support/com.apple.idleassetsd/Customer/entries.json'
aerial_folder_path='/Library/Application Support/com.apple.idleassetsd/Customer/4KSDR240FPS/'

def getAerials(path):
    aerialsList = []
    with open(path) as f:
        d = json.load(f)
        for aerial in d["assets"]:
            aerialsList.append(aerial)
    return aerialsList


def downloadAerial(url: str, file_path: str, name: str, resume_pos: int = 0):
    r = requests.head(url, verify=False)
    total = int(r.headers.get("content-length", 0))
    with requests.get(url, stream=True, headers={"Range": f"bytes={resume_pos}-"}, verify=False) as r:
        r.raise_for_status()

        with open(file_path, "wb" if resume_pos == 0 else "ab") as f:
            with tqdm.tqdm(
                desc=name,
                total=total,
                miniters=1,
                unit="B",
                unit_scale=True,
                unit_divisor=1024,
                initial=resume_pos,
            ) as pb:
                for chunk in r.iter_content(chunk_size=32 * 1024):
                    f.write(chunk)
                    pb.update(len(chunk))


def updateSQL():
    con = sqlite3.connect("/Library/Application Support/com.apple.idleassetsd/Aerial.sqlite")
    cur = con.cursor()
    cur.execute("VACUUM;")
    cur.execute("UPDATE ZASSET SET ZLASTDOWNLOADED = 718364962.0204;")
    con.commit()
    con.close()

def killService():
    #idleassetsd
    subprocess.run(["killall", "idleassetsd"])

def downloadAerialsParallel(aerial, max_retry = 5):
    if 'url-4K-SDR-240FPS' in aerial:
        url = aerial["url-4K-SDR-240FPS"].replace('\\', '')
        file_path = aerial_folder_path + aerial["id"] + '.mov'
        is_download_complete = os.path.exists(file_path)
        retry = 0
        while not is_download_complete and retry < max_retry:
            try:
                resume_pos = os.path.getsize(file_path + ".downloading") if os.path.exists(file_path + ".downloading") else 0
                downloadAerial(url, file_path + ".downloading", f"{aerial['accessibilityLabel']}: {aerial['id']}.mov", resume_pos=resume_pos)
                os.rename(file_path + ".downloading", file_path)
                is_download_complete = True
            except ChunkedEncodingError | ProtocolError as e:
                retry += 1
                if retry >= 5:
                    print(
                        f"Error downloading {aerial['accessibilityLabel']}: {aerial['id']}.mov. "
                        f"Maximum retries reached. {repr(e)}."
                    )
            except Exception as e:
                print(f"Error downloading {aerial['accessibilityLabel']}: {aerial['id']}.mov. {repr(e)}")



def chooseCategory():
    chosen_category_obj = {}
    with open(json_file_path) as f:
        data = json.load(f)

        # Display a choice of aerials categories
        print("Select aerial category:")

        categories = []
        i = 0
        for category in data['categories']:
            i=i+1
            print(str(i)+'. '+category['localizedNameKey'].replace('AerialCategory', ''))
            categories.append(category['localizedNameKey'])

        categories.append('All')
        print(str(i+1)+'. All')

        choice = input("Enter category number: ")
        chosen_category = categories[int(choice)-1]
        if chosen_category != 'All':
            chosen_category_obj = {}
            for category in data['categories']:
                if category['localizedNameKey'] == chosen_category:
                    chosen_category_obj = category
                    break
    return chosen_category_obj

def chooseSubcategory(categoryObj):
    chosen_subcategory_obj = {}
    with open(json_file_path) as f:
        data = json.load(f)
        # Get subcategories
        subcategories = []
        j = 0
        # Print subcategories
        print("Select a subcategory in "+categoryObj['localizedNameKey'].replace('AerialCategory', '')+":")
        for subcat in categoryObj['subcategories']:
            j=j+1
            print(str(j)+'. '+subcat['localizedNameKey'].replace('AerialSubcategory', ''))
            subcategories.append(subcat['localizedNameKey'])

        subcategories.append('All')
        print(str(j+1)+'. All')

        choice = input("Enter subcategory number: ")
        chosen_subcategory = subcategories[int(choice)-1]
        if chosen_subcategory != 'All':
            chosen_subcategory_obj = {}
            for subcat in categoryObj['subcategories']:
                if subcat['localizedNameKey'] == chosen_subcategory:
                    chosen_subcategory_obj = subcat
                    break
    return chosen_subcategory_obj


def chooseAerials():
    categoryObj = {}
    subcategoryObj = {}

    categoryObj = chooseCategory()
    if categoryObj!= {}:
        subcategoryObj = chooseSubcategory(categoryObj)

    aerials = getAerials(json_file_path)

    filteredAerials = []
    aerials_set = set()
    for a in aerials:
        if categoryObj == {}:
            if a['id'] not in aerials_set:
                aerials_set.add(a['id'])
                filteredAerials.append(a)
        else:
            for cat in a["categories"]:
                if cat == categoryObj['id']:
                    if a['id'] not in aerials_set:
                        aerials_set.add(a['id'])
                        filteredAerials.append(a)
            if subcategoryObj!= {}:
                for sub in a["subcategories"]:
                    if sub == subcategoryObj['id']:
                        if a['id'] not in aerials_set:
                            aerials_set.add(a['id'])
                            filteredAerials.append(a)

    print("Downloading "+str(len(filteredAerials))+" aerials")

    # Get the number of download threads from the environment variable
    download_threads = int(os.environ.get('DOWNLOAD_THREADS', 1))
    max_retry = 5
    with ThreadPoolExecutor(max_workers=download_threads) as executor:
        executor.map(downloadAerialsParallel, filteredAerials, [max_retry]*len(filteredAerials))


print("Loading Aerials list")
chooseAerials()
print("Updating Aerials Database")
updateSQL()
print("Restarting service")
killService()