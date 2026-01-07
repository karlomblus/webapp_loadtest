# webapp_loadtest
Creating a load on the web application

mitte benchmark vaid pigem tavalise kasutajakoormuse simuleerimine



# Kasutus

python3.9 koormustest.py -u https://rakenduse.url/ -c 10 -n 1 -t 3 -k


-c kasutajate hulk

-n päringut sekundis (kõigi kasutajate peale kokku)

-t testi tööaeg sekundites

-k ignoreerib SSL vigu


# Conffail


Igal päringul valitakse request.txt failist suvaline rida, mille järgi tehakse päring rakendusele

Faili formaat:

METHOD url {headers} post_payload

Näidised:

POST /url1 {'content-type':'application/json'} {"arhiivis":"false","varaLiik":"MAA"}

POST /url2 {} Suvaline data, mis läheb POST-iga kaasa

GET /url3/staticleht.js {}
