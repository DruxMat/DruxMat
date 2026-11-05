# DRUXMAT PREMIUM — GOTOWY PROJEKT, LOKALNIE I ONLINE

## A. Uruchomienie na Twoim Windows (bez hostingu)
1. Rozpakuj ZIP na komputerze (nie uruchamiaj programu bezpośrednio z ZIP).
2. Kliknij dwukrotnie `URUCHOM-STRONE-WINDOWS.bat`.
3. Potrzebujesz Pythona 3.10+ i internetu do jednorazowego pobrania bibliotek.
4. W przeglądarce otworzy się panel administratora pod `http://127.0.0.1:5000/admin/logowanie`.
5. Użyj loginu `DruxMatAdmin` i hasła przekazanego w poprzedniej rozmowie.
6. Strona główna: `http://127.0.0.1:5000/` — zamówienia klientów działać będą lokalnie na tym komputerze.

Aby strona była dostępna dla innych w internecie, wymagany jest **hosting**, a nie otwieranie pliku HTML. Nie wystawiaj developerskiego portu 5000 bezpośrednio do sieci.

## B. Uruchomienie online — Railway
Ten projekt jest przygotowany do wdrożenia jako **Flask + Gunicorn** przez `Dockerfile`. Prawdziwy publiczny URL może zostać utworzony dopiero na Twoim koncie hostingowym.

1. Utwórz projekt Railway, połącz repozytorium z plikami w tym folderze lub użyj Railway CLI (`railway up`). Nie publikuj katalogu `instance/` ani plików z hasłami.
2. W **Variables** ustaw: `SECRET_KEY` (nowy losowy sekret min. 32 znaki), `COOKIE_SECURE=1`, `DRUXMAT_ADMIN_LOGIN=DruxMatAdmin`, `DRUXMAT_ADMIN_EMAIL=druxmat@gmail.com`, `DRUXMAT_ADMIN_INITIAL_PASSWORD` (NOWE mocne hasło ustawione prywatnie w hostingu).
3. Dodaj **Volume** z punktem montowania `/data`, by nie tracić kont, zamówień i załączników po restarcie. Wolumen Railway jest montowany jako root; skrypt startowy ustawia właściciela danych, następnie uruchamia serwer na koncie bez uprawnień administratora systemu.
4. Przejdź do usługi -> Settings -> Networking -> **Generate Domain**. Railway pokaże publiczny adres HTTPS.
5. Ustaw `PUBLIC_BASE_URL=https://twoj-publiczny-adres` w Variables.
6. Włącz **SMTP** dla odzyskiwania hasła: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` (nadawca musi być akceptowany przez usługę pocztową). Bez SMTP odzyskiwanie hasła będzie niedostępne.
7. Wejdź na `https://twoj-publiczny-adres/admin/logowanie`, zaloguj się loginem `DruxMatAdmin` i NOWYM hasłem ustawionym w kroku 2.
8. Po pierwszym poprawnym uruchomieniu usuń zmienną `DRUXMAT_ADMIN_INITIAL_PASSWORD` z hostingu; konto pozostanie w trwałej bazie, a jego hasło nie zostanie zresetowane przy restarcie.
9. Włącz backupy wolumenu i przetestuj rejestrację, zamówienie ze zdjęciem, panel admina i odzyskiwanie hasła. Do produkcji uzupełnij politykę prywatności/RODO.

**UWAGA:** publiczna wersja nie ma domyślnego ani zaszytego hasła administratora. Konto startowe jest tworzone tylko przy pierwszym uruchomieniu z `DRUXMAT_ADMIN_INITIAL_PASSWORD`. Lokalna wersja ma przygotowaną bazę z poprzednim kontem, ale baza w `instance/` jest wykluczona z publikacji i obrazu Docker.

## Adresy funkcji
- `/` — strona główna
- `/rejestracja` — rejestracja klienta
- `/logowanie` — logowanie klienta
- `/zamowienie/nowe` — wysłanie zamówienia i załączników (po logowaniu)
- `/moje-zamowienia` — panel klienta
- `/admin/logowanie` — osobna strona logowania administratora
- `/admin` — panel zarządzania
- `/odzyskaj-haslo` — odzyskiwanie hasła (wymaga SMTP)
- `/health` — techniczne sprawdzenie działania serwera

Kontakt: druxmat@gmail.com, tel. 577 636 936.

## Bezpieczeństwo
- Hasła przechowywane jako hashe scrypt; prywatne załączniki wymagają odpowiedniego konta.
- CSRF, ciasteczka HttpOnly/SameSite, ograniczenie prób logowania, ograniczenia i weryfikacja plików.
- Jednorazowe tokeny resetu wygasają po 30 minutach; nowe hasło wylogowuje stare sesje.
- W publicznym serwerze wymagany `SECRET_KEY` i ciasteczka HTTPS. Dbaj o backupy i aktualizacje zależności.

## Testowanie
Zależności: `pip install -r requirements.txt pytest`. Uruchom `pytest -q test_app.py`.
Sprawdzenie kodu Python bez uruchamiania Flaska: `python -m compileall -q app.py setup_admin.py start_local.py test_app.py`.

Pliki w katalogu `demo/` są wyłącznie wizualnym podglądem, nie umożliwiają prawdziwego logowania.
