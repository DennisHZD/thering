# Price Watch

Een eigen "Tweakers Pricewatch" voor willekeurige product-URL's, met een **webapp** om alles te beheren. Draait gratis op GitHub: GitHub Actions controleert de prijzen, GitHub Pages host de webapp. Er is geen eigen server nodig.

**In de webapp:** inloggen, URL plakken, kortingspercentage of doelprijs invullen en op *Toevoegen* klikken. Binnen ongeveer een minuut staat de eerste prijs erbij. Ook mailinstellingen, controlefrequentie, bewerken, pauzeren en verwijderen regel je daar.

- Controle elke 10, 15, 30 of 60 minuten (in te stellen in de app)
- Prijsgeschiedenis met grafiek per product
- **Nepkortingen herkennen**: korting wordt berekend t.o.v. de *tijdgewogen mediaan van 30 dagen*, niet t.o.v. de "van"-prijs van de winkel. Een prijs die vlak voor een actie wordt opgehoogd telt nauwelijks mee, en je krijgt een waarschuwing.
- E-mail via Gmail, Outlook of een andere SMTP-server, plus optioneel een pushmelding via [ntfy.sh](https://ntfy.sh)

## Eenmalige installatie (±5 minuten)

1. **Repository maken**: ga naar <https://github.com/new>, kies een naam (bijv. `price-watch`) en zet hem op **Public**. Klik daarna op *uploading an existing file* en sleep de **inhoud** van deze map erin. Let op: de map `.github` moet ook mee. Werkt slepen daarvoor niet, gebruik dan GitHub Desktop of `git push`.
2. **Webapp aanzetten**: ga in de repository naar *Settings → Pages* en kies bij *Branch* `main` en map `/docs`. Klik op *Save*. Na een minuut staat de app op `https://<jouw-gebruikersnaam>.github.io/price-watch/`.
3. **Token maken**: open de app. Op het inlogscherm staat onder *Hoe maak ik een token aan?* stap voor stap hoe je een token aanmaakt. Het token heeft alleen toegang tot deze ene repository.
4. **Inloggen** → profiel aanmaken (je naam) → *Instellingen*: het gedeelde verzendaccount en je eigen e-mailadres invullen → *Testmelding sturen*.

Klaar. Vanaf dan doe je alles in de app.

### Met z'n tweeën (of meer)
Iedereen heeft een eigen **profiel** met een eigen productlijst en een eigen e-mailadres en pushtopic. Je krijgt alleen meldingen over producten die je zelf volgt. Het verzendaccount (SMTP) wordt gedeeld.

Zo laat je je partner meedoen:
1. Maak een tweede token aan (zie het inlogscherm), bijvoorbeeld met de naam `Price Watch – Sanne`, en geef dat aan je partner. Je kunt het later los intrekken.
2. Je partner opent de app, logt in met dat token en kiest *Nieuw profiel*.
3. Daarna vult je partner bij *Instellingen → Mijn meldingen* een eigen e-mailadres in.

Met *Mijn producten* / *Iedereen* wissel je tussen je eigen lijst en die van iedereen. Via de knop met je naam rechtsboven wissel je van profiel. Dit is een scheiding voor het gemak, geen beveiliging: wie kan inloggen, kan ook de producten van de ander zien en aanpassen.

### Gmail instellen
Zet [2-stapsverificatie](https://myaccount.google.com/security) aan en maak een [app-wachtwoord](https://myaccount.google.com/apppasswords). Vul in de app je Gmail-adres in als gebruikersnaam en het app-wachtwoord van 16 tekens als wachtwoord.

### Publiek of privé?
- **Public** (aanbevolen): onbeperkt gratis controles en GitHub Pages werkt gratis. Je productlijst en prijsgeschiedenis zijn wel zichtbaar voor wie de repository bekijkt. Mailgegevens en wachtwoorden blijven altijd geheim, want die staan versleuteld als GitHub-secrets.
- **Privé**: 2000 gratis Actions-minuten per maand, dus kies dan maximaal elke 30 minuten. GitHub Pages voor privé-repositories vereist een betaald GitHub Pro-account.

## Hoe werkt het alarm?

Bij elke meting wordt de nieuwe prijs vergeleken met de afgelopen 30 dagen:

| Regel | In de app |
|---|---|
| Prijs ≥ X% onder de tijdgewogen mediaan | *Korting ≥ %* |
| Prijs ≤ doelprijs | *of prijs ≤ €* |
| Laagste prijs ooit gemeten | Meer opties |
| Alleen als het ook de laagste prijs van de periode is | Meer opties |

Voorbeeld van een nepkorting: 30 dagen € 100, twee dagen opgehoogd naar € 150, dan een "actie" van € 120. De mediaan blijft € 100, dus de echte korting is −20% en je krijgt **geen alarm**.

Je krijgt één mail per prijsdaling. Een nieuwe mail volgt pas bij een nóg lagere prijs, of nadat de korting eerst weer verdwenen is. Lukt het uitlezen 12 keer op rij niet, dan krijg je één foutmail.

## Realtime?

Dit heet **web scraping**: de productpagina wordt periodiek opgehaald en de prijs wordt eruit gelezen. Echt realtime kan niet. GitHub start geplande controles bovendien vaak 5 tot 15 minuten later dan ingesteld. Vaker dan elke 10 minuten controleren kan ervoor zorgen dat winkels je blokkeren.

## Als de prijs niet gevonden wordt

De prijs wordt automatisch gelezen uit de gestructureerde productgegevens van de pagina. Bij Coolblue is dat getest en werkt het. Lukt het niet, dan zie je dat op de productkaart. Open dan *Bewerken*:

1. Zet **Pagina laden met JavaScript** aan. De pagina wordt dan in een echte browser geladen.
2. Of vul een **CSS-selector** in: klik met de rechtermuisknop op de prijs → *Inspecteren* en neem de class over, bijv. `.sales-price__current`.
3. Sommige winkels, zoals bol.com en Amazon, blokkeren verzoeken vanaf GitHub-servers. Als optie 1 ook niet helpt, is draaien vanaf een eigen computer of thuisserver de enige oplossing.

## Lokaal draaien / ontwikkelen

```bash
pip install -r requirements.txt
python -m pricewatch.main --dry-run --force   # test zonder mailen/opslaan
python -m pytest                              # tests
```

## Bestanden

```
docs/index.html                  webapp (GitHub Pages)
docs/sealedbox.js                versleuteling van secrets in de browser
products.json                    productlijst + instellingen (beheerd door de webapp)
data/history.json                prijsgeschiedenis (bijgewerkt door GitHub Actions)
pricewatch/                      Python: ophalen, analyseren, mailen
.github/workflows/check-prices.yml   geplande controle
```
