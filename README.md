django-pistoke
==============

Django-Websocket-laajennos


Järjestelmävaatimukset
----------------------
Python 3.6 tai uudempi
Django 3.0 tai uudempi

ASGI-palvelinohjelmisto: Daphne, Uvicorn tms.


Käyttöönotto
------------
Luo tai muokkaa Django-projektin ASGI-määritystiedosto seuraavan esimerkin mukaisesti:

```python
# projekti/asgi.py

import os
from django.core.asgi import get_asgi_application
from pistoke.kasittelija import WebsocketKasittelija

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'projekti.asetukset')

kasittelija = {
  'http': get_asgi_application(),
  'websocket': WebsocketKasittelija(),
}

async def application(scope, receive, send):
  return await kasittelija.get(scope['type'])(scope, receive, send)
```


Ohjaimet (middleware)
---------------------
Tavanomaiset Django-ohjaimet ajetaan Websocket-pyynnölle soveltuvin osin samalla tavoin kuin HTTP-pyynnölle.

CSRF-ohjainta muokataan siten, että saapuvan Websocket-pyynnön CSRF-tunnistetta ei yritetä tarkistaa ohjaimessa (sitä ei ole saatavilla ilman POST-dataa). Sen sijaan pyynnölle lisätään metodi `_tarkista_csrf` Websocket-yhteyden kautta vastaanotetun CSRF-datan tarkistamiseksi ajonaikaisesti.

Pistoke-sovellus lisää oman ohjaimensa (`pistoke.ohjain.WebsocketOhjain`), joka asettaa saapuvalle HTTP-pyynnölle määritteen `websocket`, joka sisältää URI-osoitteen Websocket-pyyntöjen ohjaamiseksi samalle palvelimelle kuin kyseinen HTTP-pyyntö. Mikäli alkuperäinen HTTP-pyyntö on salattu (`https://`), käytetään myös tässä URI-osoitteessa salattua Websocket-protokollaa (`wss://`).


Websocket-näkymä
----------------
Saapuvat HTTP- ja Websocket-pyynnöt ohjataan Django-näkymille tavanomaisen `urlpatterns`-reititystaulun mukaisesti. Websocket-pyynnön metodiksi (`request.method`) asetetaan `Websocket`, jolloin `django.views.generic.View.dispatch` ohjaa sen käsiteltäväksi näkymäluokan `websocket`-metodiin. Tämän metodin tulee olla asynkroninen: tyyppiä `async def`.

Huomaa, että `websocket`-metodi pitää erikseen sallia näkymäluokalle, jotta tämän tyyppiset pyynnöt sallitaan. Saateluokka `pistoke.nakyma:WebsocketNakyma` tekee tämän automaattisesti.

Websocket-toiminnallisuus voidaan ottaa käyttöön näkymäkohtaisesti esimerkiksi seuraavasti:
```python
# sovellus/nakymat.py

from django.views import generic

from pistoke.nakyma import WebsocketNakyma

class Nakyma(WebsocketNakyma, generic.TemplateView):
  template_name = 'sovellus/nakyma.html'

  async def websocket(self, request, *args, **kwargs):
    while True:
      syote = await request.receive()
      if isinstance(syote, str):
        await request.send(
          f'Kirjoitit "{syote}".'
        )
      elif isinstance(syote, bytes):
        await request.send(
          f'Kirjoitit "{syote.decode("latin-1")}".'.encode('latin-1')
        )
```

```html
<!-- sovellus/templates/sovellus/nakyma.html -->
<input id="syote" type="text" placeholder="Syötä viesti"/>
<button onClick="websocket.send(document.getElementById("syote").value);">Lähetä</button>
<script>
  websocket = new WebSocket(
    "{{ request.websocket }}{{ request.path }}"
  );
  websocket.onmessage = function (e) { alert(e.data); };
</script>
```


Xterm-näkymä
------------
Pakettiin sisältyy valmis toteutus vuorovaikutteisen pääteistunnon tarjoamiseen Web-sivun kautta käyttäjälle. Pääte on toteutettu `Xterm.js`-vimpaimen avulla. Vimpain ohjaa Websocket-yhteyden läpi palvelimella olevaa TTY-tiedostokuvaajaa, joka puolestaan ohjaa PTY-päätettä, johon voidaan liittää haluttu, vuorovaikutteinen istunto (esim. `bash`).

Seuraava esimerkki `bash`-pääteyhteyden käyttöönotosta lähettää tavanomaisen Django-CSRF-tunnisteen Websocket-pyynnön mukana (JSON-muodossa) ja tarkistaa sen ennen istunnon avaamista.
```python
# sovellus/bash.py

import json
import subprocess

from pistoke.xterm import XtermNakyma

class Komentokeskusnakyma(XtermNakyma):
  template_name = 'sovellus/bash.html'

  def prosessi(self):
    subprocess.run(['/bin/bash'])

  async def websocket(self, request, *args, **kwargs):
    data = json.loads(await request.receive())
    if not request._tarkista_csrf(data.get('csrfmiddlewaretoken')):
      return await request.send(
        '\033[31mCSRF-avain puuttuu tai se on virheellinen!\033[0m'
      )
    await super().websocket(request, *args, **kwargs)
```

```html
<!-- sovellus/bash.html -->
{% extends "pistoke/xterm.html" %}

{% block sisalto %}
  <form id="avaa" method="POST">
    {% csrf_token %}
    <input type="submit" value="Suorita"/>
  </form>
  <hr/>
  {{ block.super }}
{% endblock sisalto %}

{% block skriptit %}
  {{ block.super }}
  <script>
    document.getElementById("avaa").onsubmit = function (e) {
      e.preventDefault();
      var formData = new FormData(e.target);
      var lomake = {};
      formData.forEach(function (value, key) {
        lomake[key] = value;
      });
      avaa_xterm(function (ws) { ws.send(JSON.stringify(lomake)); });
    };
  </script>
{% endblock skriptit %}
```


ASGI-palvelimen ajaminen työasemalla
------------------------------------

Paketti muokkaa Djangon tavanomaista `runserver`-komentoa (tai `staticfiles`-sovelluksen muokkaamaa versiota siitä) seuraavasti:
- mikäli `uvicorn` on asennettu, käynnistetään oletuksena ASGI-palvelin sen avulla;
- vipu `--wsgi` käynnistää tällöin sen sijaan tavanomaisen WSGI-palvelimen.

ASGI-toteututuksena voidaan käyttää myös vaikkapa Daphnea seuraavasti:
```bash
daphne projekti.asgi:application
```


ASGI-palvelin testi- tai tuotantokäytössä
-----------------------------------------
Ks. vaikkapa https://www.uvicorn.org/deployment/#running-behind-nginx
