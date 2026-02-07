# webapp_loadtest
Creating a load on the web application

mitte benchmark vaid pigem tavalise kasutajakoormuse simuleerimine



# Kasutus

python3.9 koormustest.py -u https://rakenduse.url/ -c 10 -n 1 -t 3 -k

-u serveri baas-URL

-c kasutajate hulk

-n päringut sekundis (kõigi kasutajate peale kokku)

-t testi tööaeg sekundites

-f päringute fail (vaikimisi requests.txt)

-s startup päringute fail (vaikimisi startup_requests.txt)

--timeout päringu timeout sekundites (vaikimisi 30.0)

-k ignoreerib SSL vigu

-h abiinfo


# Näited

`python3.9 koormustest.py -u https://example.com -c 20 -n 10 -t 30`

`python3.9 koormustest.py -u https://example.com -c 5 -n 2 -t 10 -f requests.txt -k`

`python3.9 koormustest.py -u https://example.com -c 10 -n 5 -t 60 -s init.txt --timeout 5.5`


# Conffail


Igal päringul valitakse päringute failist (vaikimisi `requests.txt`) suvaline rida, mille järgi tehakse päring rakendusele

Faili formaat:

METHOD url {headers} post_payload

Näidised:

POST /url1 {'content-type':'application/json'} {"arhiivis":"false","varaLiik":"MAA"}

POST /url2 {} Suvaline data, mis läheb POST-iga kaasa

GET /url3/staticleht.js {}
