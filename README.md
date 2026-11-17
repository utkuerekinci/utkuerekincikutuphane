# Utku Erekinci Kütüphanesi

Bu proje Python, Flask ve SQLite uyumlu Turso kullanılarak geliştirilmiş bir kütüphane veritabanı uygulamasıdır. Kitap, yazar ve yayınevi kayıtlarını listeler; form üzerinden yeni kitap kaydı ekler.

Canlı site: https://utkuerekincikutuphane.vercel.app/

## Veritabanı

- Vercel'de `TURSO_DATABASE_URL` ve `TURSO_AUTH_TOKEN` ortam değişkenleri tanımlanır ve uygulama Turso'ya bağlanır. Bunlar GitHub'a yazılmaz.
- Yerelde, ortam değişkenleri tanımlı değilse `utkuerekincikutuphane.db` kullanılır.
- Yeni kitap kayıtları Vercel'de Turso'ya yazılır; dağıtımlar arasında kalır.

## Kurulum

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```
