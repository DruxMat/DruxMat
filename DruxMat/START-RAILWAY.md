# DruxMat Premium — publikacja na Railway

Projekt uruchamia Flask/Gunicorn jako usługę Docker. Nie publikuj lokalnej bazy klientów.

1. Wejdź do [Railway](https://railway.com), zaloguj się i utwórz projekt. Wybierz wdrożenie z prywatnego repozytorium GitHub z plikami paczki ONLINE. Alternatywnie z katalogu projektu uruchom `railway up` przy użyciu Railway CLI.
2. Przed pierwszym poprawnym startem w zakładce **Variables** dodaj poniższe zmienne (wartości SECRET_KEY i hasła ustaw samodzielnie, nie w repozytorium):

   | Zmienna | Wartość |
   |---|---|
   | `SECRET_KEY` | losowy sekret min. 32 znaki, np. wynik `python -c "import secrets; print(secrets.token_hex(32))"` |
   | `COOKIE_SECURE` | `1` |
   | `DRUXMAT_ADMIN_LOGIN` | `DruxMatAdmin` |
   | `DRUXMAT_ADMIN_EMAIL` | `druxmat@gmail.com` (potwierdź, że masz dostęp do skrzynki) |
   | `DRUXMAT_ADMIN_INITIAL_PASSWORD` | nowe, unikalne hasło min. 12 znaków |

3. W usłudze Railway dodaj **Volume** z punktem montowania **`/data`**. To krytyczne: baza danych i zdjęcia muszą przetrwać ponowne wdrożenia. Po podpięciu wolumenu upewnij się, że aplikacja uruchamia się bez błędów. **Nie uruchamiaj więcej niż jednej repliki usługi z SQLite na tym wolumenie.**
4. W **Settings → Networking** wybierz **Generate Domain**. Otrzymasz prawdziwy publiczny link HTTPS do strony. Dopisz w Variables `PUBLIC_BASE_URL=https://uzyskany-adres`.
5. Aby działało „Nie pamiętam hasła”, skonfiguruj dostawcę poczty SMTP: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`. Nadawca musi być zweryfikowany i dopuszczony przez dostawcę poczty. Sam kontaktowy adres Gmail bez skonfigurowanej poczty SMTP nie wystarczy.
6. Sprawdź: `/health` powinien zwrócić `ok`; `/admin/logowanie` umożliwia zalogowanie loginem `DruxMatAdmin` i **nowym** hasłem. Przetestuj rejestrację klienta, zamówienie z załącznikiem, uprawnienia i e-mail odzyskiwania hasła.
7. Po aktywacji konta usuń zmienną `DRUXMAT_ADMIN_INITIAL_PASSWORD` z Railway i ponownie wdróż usługę; nie zmieni to hasła zapisanego w trwałej bazie. Włącz kopie zapasowe wolumenu, sprawdź politykę prywatności i regularnie aktualizuj zależności.

**Bezpieczeństwo:** Nie kopiuj lokalnego katalogu `instance/` ani bazy `.sqlite3` do Railway / GitHub. W sieci nie używaj wcześniejszego hasła z rozmowy. Dane klientów są wrażliwe.

Informacje o uruchamianiu: https://docs.railway.com/quick-start i https://docs.railway.com/cli/deploying
