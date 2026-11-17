"""Utku Erekinci Kütüphanesi: Vercel'de Turso, yerelde SQLite."""

from datetime import date
from pathlib import Path
import os
import sqlite3

from flask import Flask, render_template, request, redirect, url_for

app = Flask(__name__)

YEREL_DB = Path(__file__).resolve().parent / "utkuerekincikutuphane.db"


def baglanti_ac():
    """Vercel'de kalıcı Turso veritabanına; yerelde SQLite dosyasına bağlan."""
    url = os.environ.get("TURSO_DATABASE_URL")
    token = os.environ.get("TURSO_AUTH_TOKEN")

    if url and token:
        import libsql
        return libsql.connect(database=url, auth_token=token)

    # Yanlış yapılandırılmış bir yayında sessizce geçici SQLite'a geçme.
    if os.environ.get("VERCEL"):
        raise RuntimeError(
            "TURSO_DATABASE_URL ve TURSO_AUTH_TOKEN Vercel ortamında tanımlanmalı."
        )

    return sqlite3.connect(YEREL_DB, timeout=10)


def sozluk_kayitlar(cursor):
    """sqlite3 ve libsql cursor sonuçlarını şablona uygun sözlüğe dönüştür."""
    sutunlar = [bilgi[0] for bilgi in cursor.description]
    return [dict(zip(sutunlar, satir)) for satir in cursor.fetchall()]


@app.route("/", methods=["GET", "POST"])
def anasayfa():
    hata = None
    basarili = request.args.get("eklendi") == "1"
    form = request.form if request.method == "POST" else {}
    db = baglanti_ac()

    try:
        if request.method == "POST":
            kitap_adi = request.form.get("kitap_adi", "").strip()

            try:
                basim_yili = int(request.form.get("basim_yili", ""))
                fiyat = int(request.form.get("fiyat", ""))
                yazar_id = int(request.form.get("yazar_id", ""))
                yayinevi_id = int(request.form.get("yayinevi_id", ""))
            except ValueError:
                hata = "Basım yılı, fiyat, yazar ve yayınevi alanlarını kontrol edin."
            else:
                if not kitap_adi:
                    hata = "Kitap adını yazın."
                elif len(kitap_adi) > 200:
                    hata = "Kitap adı 200 karakterden uzun olamaz."
                elif not (1000 <= basim_yili <= date.today().year + 1):
                    hata = "Geçerli bir basım yılı girin."
                elif fiyat < 0:
                    hata = "Fiyat sıfırdan küçük olamaz."
                else:
                    yazarlar = sozluk_kayitlar(db.execute(
                        'SELECT YazarID, YazarAdi, YazarSoyadi FROM "Yazarlar" WHERE YazarID = ?',
                        (yazar_id,),
                    ))
                    yayinevleri = sozluk_kayitlar(db.execute(
                        'SELECT YayineviID, YayineviAdi FROM "YayınEvleri" WHERE YayineviID = ?',
                        (yayinevi_id,),
                    ))

                    if not yazarlar or not yayinevleri:
                        hata = "Listeden geçerli bir yazar ve yayınevi seçin."
                    else:
                        yazar = yazarlar[0]
                        yayinevi = yayinevleri[0]
                        yazar_adi = f"{yazar['YazarAdi']} {yazar['YazarSoyadi']}".strip()
                        db.execute(
                            '''INSERT INTO "Kitaplar"
                               (KitapAdi, KitapBasimYili, KitapYazarAdi,
                                KitapYayinevi, YazarID, YayinEviID, Fiyat)
                               VALUES (?, ?, ?, ?, ?, ?, ?)''',
                            (
                                kitap_adi, basim_yili, yazar_adi,
                                yayinevi["YayineviAdi"], yazar_id,
                                yayinevi_id, fiyat,
                            ),
                        )
                        db.commit()
                        return redirect(url_for("anasayfa", eklendi="1"))

        yazarlar = sozluk_kayitlar(db.execute(
            'SELECT YazarID, YazarAdi, YazarSoyadi FROM "Yazarlar" '
            'ORDER BY YazarAdi, YazarSoyadi'
        ))
        yayinevleri = sozluk_kayitlar(db.execute(
            'SELECT YayineviID, YayineviAdi FROM "YayınEvleri" ORDER BY YayineviAdi'
        ))

        tablolar = {}
        for tablo in ("Kitaplar", "Yazarlar", "YayınEvleri"):
            sutunlar = db.execute(f'PRAGMA table_info("{tablo}")').fetchall()
            kayitlar = db.execute(f'SELECT * FROM "{tablo}"').fetchall()
            tablolar[tablo] = {
                "sutunlar": [sutun[1] for sutun in sutunlar],
                "veriler": [list(kayit) for kayit in kayitlar],
            }

        return render_template(
            "index.html", tablolar=tablolar, yazarlar=yazarlar,
            yayinevleri=yayinevleri, hata=hata,
            basarili=basarili, form=form,
        )
    finally:
        db.close()


if __name__ == "__main__":
    app.run(debug=True)
