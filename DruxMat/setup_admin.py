"""Run `python setup_admin.py` to create or reset administrator credentials."""
from getpass import getpass
from app import create_admin

print('DruxMat Premium — konfiguracja administratora')
email = input('E-mail administratora (do logowania): ').strip()
login_name = input('Login administratora (np. DruxMatAdmin; Enter = tylko e-mail): ').strip() or None
password = getpass('Nowe hasło (minimum 12 znaków): ')
repeat = getpass('Powtórz hasło: ')
if password != repeat:
    raise SystemExit('Hasła nie są identyczne.')
try:
    create_admin(email, password, login_name=login_name)
except ValueError as exc:
    raise SystemExit(str(exc))
print('Gotowe. Wejdź na /admin/logowanie i użyj podanego adresu i hasła.')
