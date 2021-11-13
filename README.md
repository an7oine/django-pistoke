# django-pistoke

Django-laajennos, joka mahdollistaa Websocket-pyyntöjen käsittelemisen Django-näkymien kautta tasavertaisesti HTTP-pyyntöjen rinnalla.

Sisältää seuraavat työkalut:

* [Websocket-käsittelijä](#asgi-määritys) testi- ja tuotantokäyttöön

* [HTTP- ja Websocket-ohjaimet](#ohjaimet) (middleware)

* [asynkroninen kehityspalvelin: `manage.py runserver --asgi`](#asgi-kehityspalvelin)

* [Websocket-näkymäprotokolla](#websocket-protokolla)

* [Websocket-näkymäluokka](#websocket-näkymä)

* [tarvittavat testaustyökalut](#websocket-näkymien-testaaminen)


## Käyttöönotto

### Järjestelmävaatimukset

* Python 3.6 tai uudempi
* Django 3.1 tai uudempi
* ASGI-palvelinohjelmisto (tuotannossa): Daphne, Uvicorn, Hypercorn tms.


### Asennus

```bash
pip install django-pistoke
```

### Django-projektiasetukset

Lisää Django-projektiasetuksiin:
- `pistoke.Pistoke` asennettuihin sovelluksiin (ennen mahdollista `staticfiles`-sovellusta) ja 
- `pistoke.ohjain.WebsocketOhjain` asennettuihin ohjaimiin:
```python
# projekti/asetukset.py
...
INSTALLED_APPS = [
  ...
  'pistoke.Pistoke',
  ...
  'django.contrib.staticfiles', # tarvittaessa
  ...
]
MIDDLEWARE = [
  ...
  'pistoke.ohjain.WebsocketOhjain',
]
```

Tämä järjestys vaaditaan, jotta käsillä olevan paketin toteuttama `runserver`-komento ohittaa `staticfiles`-toteutuksen.

Jakeluun sisältyvä [`django-protoni`](https://pypi.org/project/django-protoni/)-yhteensopiva asetuslaajennos (pistoke/asetukset.py) tekee nämä lisäykset automaattisesti.


### ASGI-määritys

Luo tai täydennä Django-projektin ASGI-määritystiedosto. Alla kuvattu esimerkkimääritys:
- alustaa Django-oletuskäsittelijän HTTP-pyynnöille,
- alustaa Pistoke-käsittelijän Websocket-pyynnöille ja
- ajaa kunkin saapuvan ASGI-pyynnön oikean käsittelijän läpi, jolloin pyyntö ohjautuu tavanomaisen Django-reititystaulun (`ROOT_URLCONF`) mukaiselle näkymälle riippumatta sen tyypistä.

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


## Ohjaimet

### Ohjaimet HTTP-pyynnöllä

Käsillä oleva paketti sisältää tavanomaisen Django/HTTP-ohjaimen `pistoke.ohjain.WebsocketOhjain`, joka asettaa saapuvalle HTTP-pyynnölle määritteen `websocket`.
- tämä sisältää URI-osoitteen, esim. `ws://palvelin.org`, Websocket-pyyntöjen ohjaamiseksi samalle palvelimelle (`http://palvelin.org`) kuin kyseinen HTTP-pyyntö;
- mikäli HTTP-yhteys on salattu (esim. `https://palvelin.org`), käytetään salattua Websocket-protokollaa: `wss://palvelin.org`.

### Ohjaimet Websocket-pyynnöllä

Tavanomaiset Django-ohjaimet ajetaan Websocket-pyynnölle samalla tavoin kuin HTTP-pyynnölle, pl. HTTP-paluusanoman käsittely.

CSRF-ohjainta muokataan siten, että saapuvan Websocket-pyynnön CSRF-tunnistetta ei yritetä tarkistaa ohjaimessa (sitä ei ole saatavilla ilman POST-dataa). Sen sijaan pyynnölle lisätään metodi `tarkista_csrf` Websocket-yhteyden kautta vastaanotetun CSRF-datan tarkistamiseksi ajonaikaisesti.

Lisäksi Websocket-pyynnöille käytetään ohjainta, joka tarkistaa web-selaimen asettaman `Origin`-otsakkeen arvon. Ohjain hyväksyy oletusarvoisesti vain `ALLOWED_HOSTS`-asetuksen mukaiset pyyntölähteet; muista lähteistä tuleville pyynnöille palautuu hylkäävä paluusanoma (403).


## Websocket-protokolla

Kullekin Websocket-pyyntöjä käsittelevälle näkymälle on määriteltävä protokolla, jonka mukaan yhteys luodaan ja katkaistaan ja viestinvälitys tapahtuu.

Näkymä voi joko
- itse toteuttaa ASGI-määrityksen mukaisen viestinvaihdon (`{"type": "websocket.connect"}`, `{"type": "websocket.send", "text": "..."}` jne.),
- käyttää käsillä olevan paketin tarjoamaa protokollatoteutusta: `pistoke.protokolla.WebsocketProtokolla` ja sen alaluokat; tai
- käyttää oletusarvoista protokolla joka otetaan automaattisesti käyttöön.

Protokollaa käytetään sellaisenaan koristeena Websocket-näkymäfunktiolle tai Django-`method_decoratorin` avulla koristeena näkymäluokan `websocket`-metodille.

Huomaa, että samaan näkymään liittyvien koristeiden keskinäisellä määritysjärjestyksellä on merkitystä. Kun Websocket-näkymässä käytetään protokollan `P` lisäksi esimerkiksi Django-pääsynhallintaan liittyvää koristetta `D`:
- Mikäli protokolla `P` on sisempänä (alempana) kuin `D`, palautuu käyttäjälle tavanomainen HTTP-virhesanoma 401 tai 403, kun oikeudet eivät riitä.
- Mikäli protokolla `P` on ulompana (ylempänä) kuin `D`, avautuu Websocket-yhteys normaalisti myös silloin, kun oikeudet eivät riitä. Yhteys kuitenkin päättyy tällöin heti poikkeukseen.

Huomaa, että käsillä olevan paketin toteuttama automaattinen protokollamääritys muodostaa aina uloimman kerroksen näkymän ympärillä.

Yleiskäyttöisen kantaluokan (`WebsocketProtokolla`) lisäksi käytettävissä ovat seuraavat, rajatumpiin tilanteisiin soveltuvat protokollat:
- `WebsocketAliProtokolla("protokolla-a", "protokolla-b")`: Websocket-aliprotokollamääritys
- `WebsocketJSONProtokolla`: JSON-muotoinen viestinvaihto.


### Yhteensopivuus: django-pistoke v0.x vs. v1.x

Yhteensopivuuden varmistamiseksi taaksepäin käytetään versioon 1.1 asti seuraavaa automatiikkaa:
- mikäli Websocket-näkymälle on asetettu jokin edellä mainittu protokolla, sitä käytetään sellaisenaan
- muussa tapaksessa näkymä koristellaan automaattisesti `WebsocketProtokolla`-tyyppiseksi.

Versioon 1.2 asti on lisäksi käytettävissä seuraava ohitus edellämainittuun automatiikkaan:
- mikäli näkymäluokka toteuttaa itse ASGI-viestinvaihdon, tämä voidaan määrittää `TyhjaWebsocketProtokolla`-koristetta käyttäen.


## Websocket-näkymä

[Websocket-käsittelijä](#asgi-määritys) ohjaa saapuvat pyynnöt Django-näkymille tavanomaisen `urlpatterns`-reititystaulun mukaisesti. Websocket-pyynnön metodiksi (`request.method`) asetetaan `Websocket`. Näkymän toteutus voi olla funktio- tai luokkapohjainen:
- `django.views.generic.View.dispatch` ohjaa WS-pyynnön käsiteltäväksi näkymäluokan `websocket`-metodiin;
- funktiopohjainen näkymä voi vastata pyynnön metodin perusteella eri tavoin HTTP- ja Websocket-pyyntöihin.

Kummassakin tapauksessa WS-pyynnön käsittelystä vastaavan metodin tai funktion tulee olla tyyppiä `async def`.

Huomaa, että luokkapohjaisen näkymän tapauksessa `Websocket`-metodi pitää erikseen sallia näkymäluokalle (HTTP-metodien kuten `GET` ja `POST` ohella), jotta tämän tyyppiset pyynnöt sallitaan. Saateluokka `pistoke.nakyma:WebsocketNakyma` tekee tämän automaattisesti.

Seuraava listaus on esimerkki yhdysrakenteisesta, luokkapohjaisesta näkymätoteutuksesta, joka
- palauttaa GET-pyynnöllä Django-sivuaihion ja
- vastaa Websocket-pyyntöön jatkuvana viestivaihtona:

```python
# sovellus/nakyma.py

from django.urls import path
from django.utils.decorators import method_decorator
from django.views import generic

from pistoke.nakyma import WebsocketNakyma
from pistoke.protokolla import WebsocketProtokolla

@method_decorator(WebsocketProtokolla(), name='websocket')
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
     # white True
   # async def websocket
 # class Nakyma

urlpatterns = [path('nakyma/', Nakyma.as_view())]
```

Esimerkki tähän näkymään liittyvästä HTML-aihiosta:
```html
<!-- sovellus/templates/sovellus/nakyma.html -->
<input
  id="syote"
  type="text"
  placeholder="Syötä viesti"
  />
<button
  onclick="websocket.send(document.getElementById('syote').value);"
  >Lähetä</button>
<script>
  websocket = new WebSocket(
    "{{ request.websocket }}{{ request.path }}"
  );
  websocket.onmessage = function (e) { alert(e.data); };
</script>
```


## ASGI-kehityspalvelin

Paketti sisältää `runserver`-ylläpitokomentototeutuksen (Django-kehityspalvelin), joka periytetään joko:
- Djangon tavanomaisesta `runserver`-komennosta tai
- `django.contrib.staticfiles`-sovelluksen periyttämästä komennosta, mikäli tämä on asennettu.

Käsillä olevan paketin toteuttama `runserver` lisää seuraavat vivut edellä mainittuihin toteutuksiin nähden:
- vipu `--wsgi` käynnistää tavanomaisen (sisäänrakennetun) WSGI-palvelimen;
- vipu `--asgi` käynnistää ASGI-palvelimen (`uvicorn`-pakettia käyttäen);
- oletus näistä on ASGI, jos ja vain jos `uvicorn` on asennettu.

Huomaa, että `--asgi`-vipu edellyttää [Uvicorn](https://pypi.org/project/uvicorn/)-paketin asentamisen ja aiheuttaa poikkeuksen, mikäli tätä ei löydy.

Vakiona `runserver`-komennon hyväksymä `--verbose`-vipu hyväksyy, silloin kuin käytössä on `--asgi`-tila, tavanomaisten numeroarvojensa (0–3) lisäksi myös `uvicorn --log-level`-vivun hyväksymät tekstimuotoiset määreet:
- `critical`: vastaa Django-tasoa 0
- `error`
- `warning`
- `info`: vastaa Django-tasoa 1
- `debug`: vastaa Django-tasoa 2
- `trace`: vastaa Django-tasoa 3


## Palvelinasennus

Palvelinasennukseen sopii hyvin vaikkapa yhdistelmä Nginx + Circus + Uvicorn; ks. <https://www.uvicorn.org/deployment/#running-behind-nginx>.


## Käyttöesimerkkejä

* Reaaliaikainen keskusteluyhteys kahden käyttäjän välillä: [django-juttulaatikko](https://pypi.org/project/django-juttulaatikko/)
* Datan reaaliaikainen, kaksisuuntainen synkronointi Django-palvelimen ja selaimen välillä Websocket-yhteyden välityksellä: [django-synkroni](https://pypi.org/project/django-synkroni/)
* Xterm-pääteyhteys Django-sovelluksena: [django-xterm](https://pypi.org/project/django-xterm/)
* Django-ilmoitusten (`messages`) reaaliaikainen toimitus selaimelle Celery-pinon ja Websocket-yhteyden avulla: [django-celery-ilmoitus](https://pypi.org/project/django-celery-ilmoitus/)
* jQuery-Datatables-liitännäinen Websocket-pohjaiseen tiedonsiirtoon erillisten Ajax-pyyntöjen asemesta: [datatables-websocket](https://github.com/an7oine/datatables-websocket.git)
