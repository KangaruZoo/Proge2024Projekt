################################################
# Programmeerimine I
# 2024/2025 sügissemester
#
# Projekt
# Teema: Toote Hinna Otsingu Programm
#
#
# Autorid: Jan Alar Alesmaa, Kaur Kingsepp
#
# mõningane eeskuju: Hinnavaatlus.ee
#
# Lisakommentaar (nt käivitusjuhend): Vajab chromedriver.exe. Käivitusjuhend on readme.md failis
#
##################################################

from flask import Flask, render_template, request, jsonify
import requests
import json
import re
import pandas as pd
import urllib.parse
import time
import Levenshtein
import webbrowser
import socket
from threading import Timer
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
from tabulate import tabulate

# Pandas andmeraamistiku suurim ridade arv
max_read = 20

app = Flask(__name__)

# Web scraper Maxima veebilehe jaoks. 
def maxima(sisend):
    # Kontrollime, kas sisend on olemas
    if sisend:
        page_num = 1
        maxima_tootenimed = []  # List toodete nimede jaoks
        maxima_toote_hind = []  # List toodete hindade jaoks

        while True:
            # Koostame URL-i päringu jaoks
            url = f'https://www.barbora.ee/otsing?q={sisend}&page={page_num}'
            page = requests.get(url)

            if page.status_code == 200:  # Kontrollime, kas päring oli edukas
                soup = BeautifulSoup(page.text, 'html.parser')
                # Leiame <script>-tagi, mis sisaldab toodete JSON andmeid
                script_tag = soup.find('script', string=re.compile(r'window\.b_productList = \[.*\];'))

                if script_tag:
                    # Eemaldame JSON andmed stringist
                    json_tekst = re.search(r'window\.b_productList = (\[.*\]);', script_tag.string).group(1)
                    # Parsime JSON stringi listiks
                    toote_list = json.loads(json_tekst)
                    
                    # Kui tooteid ei leidu, lõpetame tsükli
                    if not toote_list:
                        break
                    
                    # Lisame tootenimed ja hinnad vastavatesse listidesse
                    for toode in toote_list:
                        if len(maxima_tootenimed) >= max_read:
                            break
                        tootenimi = toode.get('title')
                        hind = toode.get('price')
                        maxima_tootenimed.append(tootenimi)
                        maxima_toote_hind.append(hind)
                else:
                    # Kui <script>-tagi ei leita, lõpetame tsükli
                    break
            else:
                # Kui päring ei olnud edukas, lõpetame tsükli
                break
            
            # Suurendame leheküljenumbrit järgmise lehe pärimiseks
            page_num += 1
        # Tagastame tooted ja hinnad Pandas andmeraamina
        return pd.DataFrame({'Toode': maxima_tootenimed, 'Hind': maxima_toote_hind})

# Web scraper Rimi veebilehe jaoks. 
def rimi(sisend):
    # Kontrollib, kas sisend on olemas
    if sisend:
        url = 'https://www.rimi.ee/epood/ee/otsing?query=' + sisend
        page = requests.get(url)
        rimi_tootenimed = []  # List toodete nimede jaoks
        rimi_toote_hinnad = []  # List toodete hindade jaoks

        if page.status_code == 200:  # Kontrollib, kas päring oli edukas
            soup = BeautifulSoup(page.text, 'html.parser')
            # Otsime elemendid, millel on atribuut `data-gtm-eec-product`
            rimi_elements = soup.find_all(attrs={'data-gtm-eec-product': True})
            for toote_info in rimi_elements:
                if len(rimi_tootenimed) >= max_read:
                    break
                # Laeme JSON andmed elemendist
                product_data = json.loads(toote_info['data-gtm-eec-product'])
                nimi = product_data.get('name')  # Toote nimi
                hind = product_data.get('price')  # Toote hind
                rimi_tootenimed.append(nimi)
                rimi_toote_hinnad.append(hind)
        # Tagastame tooted ja hinnad Pandas andmeraamina
        return pd.DataFrame({'Toode': rimi_tootenimed, 'Hind': rimi_toote_hinnad})


def ümberjärjesta_andmetabel(viide_df, siht_df):
    # Tulemuse salvestamiseks tühi list
    ümberjärjestatud_andmed = []
    
    # Juba kasutatud indeksid, et vältida kordusi
    kasutatud_indeksid = set()
    
    # Itereerime läbi kõik viite-andmetabeli tooted
    for viide_toode in viide_df['Toode']:
        lähim_ühilduvus = None  # Kõige sarnasem leitud siht-toode
        lähim_kaugus = float('inf')  # Kõige väiksem Levenshtein'i kaugus
        lähim_indeks = -1  # Indeks siht-andmetabelis, mis vastab kõige sarnasemale tootele
        
        # Võrdleme iga viite-toodet kõigi siht-tabeli toodetega
        for idx, siht_toode in enumerate(siht_df['Toode']):
            if idx not in kasutatud_indeksid:  # Kontrollime, et indeksit poleks juba kasutatud
                kaugus = Levenshtein.distance(viide_toode, siht_toode)  # Levenshtein'i kauguse arvutus
                if kaugus < lähim_kaugus:  # Uuendame, kui leitud on väiksem kaugus
                    lähim_kaugus = kaugus
                    lähim_ühilduvus = siht_toode
                    lähim_indeks = idx
        
        # Kui lähim vaste leiti, lisame selle rea ümberjärjestatud andmetesse
        if lähim_ühilduvus is not None:
            lähim_rida = siht_df.iloc[lähim_indeks]  # Võtame rea siht-andmetabelist
            ümberjärjestatud_andmed.append(lähim_rida)  # Lisame tulemuste hulka
            kasutatud_indeksid.add(lähim_indeks)  # Märgime indeksi kasutatuks
    
    # Loome uue DataFrame'i ümberjärjestatud andmetega ja lähtestame indeksid
    return pd.DataFrame(ümberjärjestatud_andmed).reset_index(drop=True)

def sanitize_input(sisend):
    # Remove any non-alphanumeric characters except spaces
    sanitized = re.sub(r'[^a-zA-Z0-9\s]', '', sisend)
    return sanitized

def validate_input(sisend):
    # Ensure the input is not empty and does not exceed 100 characters
    if not sisend or len(sisend) > 100:
        return False
    return True

@app.route('/')
def index():
    # Renderdame index.html
    return render_template('index.html')

@app.route('/search', methods=['POST'])
def search():
    # Saame kasutaja sisendi JSON vormingus
    sisend = request.json.get('query')
    if not sisend:
        return jsonify({"error": "Palun sisesta toode!"}), 400

    # Sanitize and validate input
    sisend = sanitize_input(sisend)
    if not validate_input(sisend):
        return jsonify({"error": "Vigane sisend!"}), 400

    # Pärib andmeid erinevatest kauplustest
    maxima_data = maxima(sisend)  # Maxima andmed
    rimi_data = rimi(sisend)  # Rimi andmed
    
    rimi_data = ümberjärjesta_andmetabel(maxima_data, rimi_data)


    # Koondab andmed ühte struktuuri
    data = {
        "Maxima": maxima_data.to_dict(orient='records'),
        "Rimi": rimi_data.to_dict(orient='records')
    }
    
    # Tagastame andmed JSON vormingus
    return jsonify(data)


if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=5000)
