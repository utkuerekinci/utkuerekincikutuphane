"""Utku Erekinci Kütüphanesi – kitap ve yazar ekleme.

Vercel: TURSO_DATABASE_URL + TURSO_AUTH_TOKEN -> kalıcı Turso.
Yerel geliştirme: proje klasöründeki utkuerekincikutuphane.db -> SQLite.
Kitap eklemenin çalışması için Turso'daki Kitaplar tablosunun foreign key
ilişkilerini ekteki SQL adımlarıyla bir kez düzeltmek gerekir.
"""

from datetime import date
from pathlib import Path
import logging
import os
import sqlite3

from flask import Flask, redirect, render_template, request, url_for

app = Flask(__name__)
YEREL_DB = Path(__file__).resolve().parent / "utkuerekincikutuphane.db"


def baglanti_ac():
    url = os.environ.get("TURSO_DATABASE_URL", "").strip()
    token = os.environ.get("TURSO_AUTH_TOKEN", "").strip()
    if url and token:
        import libsql
        return libsql.connect(database=url, auth_token=token)
    if os.environ.get("VERCEL"):
        raise RuntimeError("Vercel'de TURSO_DATABASE_URL ve TURSO_AUTH_TOKEN gerekli.")
    return sqlite3.connect(str(YEREL_DB), timeout=10)


def sozluk_kayitlar(cursor):
    basliklar = [sutun[0] for sutun in cursor.description]
    return [dict(zip(basliklar, satir)) for satir in cursor.fetchall()]


def kaydet_veya_hata(db, sql, parametreler):
    """Kayıt hatasında sunucuyu düşürmek yerine ekranda mesaj göster."""
    try:
        sonuc = db.execute(sql, parametreler)
        db.commit()
        return sonuc, None
    except Exception:
        app.logger.exception("Veritabanına kayıt eklenemedi")
        try:
            db.rollback()
        except Exception:
            app.logger.warning("Rollback başarısız", exc_info=True)
        return None, (
            "Kayıt eklenemedi. Turso'daki Kitaplar tablosunun ilişkileri "
            "düzeltildi mi? Vercel Logs bölümünü kontrol edin."
        )


def yeni_yazar_kaydet(db, veri):
    ad = veri.get("yazar_adi", "").strip()
    soyad = veri.get("yazar_soyadi", "").strip()
    dogum = veri.get("yazar_dt", "").strip()
    olum = veri.get("yazar_ot", "").strip()

    if not ad or not soyad:
        return None, "Yazarın adı ve soyadı zorunludur."
    if len(ad) > 100 or len(soyad) > 100:
        return None, "Ad ve soyad en fazla 100 karakter olabilir."
    try:
        dogum_tarihi = date.fromisoformat(dogum) if dogum else None
        olum_tarihi = date.fromisoformat(olum) if olum else None
    except ValueError:
        return None, "Doğum ve ölüm tarihlerini kontrol edin."
    if dogum_tarihi and olum_tarihi and olum_tarihi < dogum_tarihi:
        return None, "Ölüm tarihi doğum tarihinden önce olamaz."

    # Yazarlar tablosunda tarih sütunları nullable; boş tarihleri NULL olarak yaz.
    sonuc, hata = kaydet_veya_hata(
        db,
        '''INSERT INTO "Yazarlar" ("YazarAdi", "YazarSoyadi", "YazarDT", "YazarOT")
           VALUES (?, ?, ?, ?)''',
        (ad, soyad, dogum or None, olum or None),
    )
    return (sonuc.lastrowid if sonuc else None), hata


def yeni_kitap_kaydet(db, veri):
    kitap_adi = veri.get("kitap_adi", "").strip()
    if not kitap_adi:
        return "Kitap adını yazın."
    if len(kitap_adi) > 200:
        return "Kitap adı 200 karakterden uzun olamaz."

    try:
        yil = int(veri.get("basim_yili", ""))
        fiyat = int(veri.get("fiyat", ""))
        yazar_id = int(veri.get("yazar_id", ""))
        yayinevi_id = int(veri.get("yayinevi_id", ""))
    except (ValueError, TypeError):
        return "Basım yılı, fiyat, yazar ve yayınevi alanlarını kontrol edin."

    if yil < 1000 or yil > date.today().year + 1:
        return "Geçerli bir basım yılı girin."
    if fiyat < 0:
        return "Fiyat sıfırdan küçük olamaz."

    yazar = sozluk_kayitlar(db.execute(
        '''SELECT "YazarID", "YazarAdi", "YazarSoyadi" FROM "Yazarlar"
           WHERE "YazarID" = ?''', (yazar_id,)
    ))
    yayinevi = sozluk_kayitlar(db.execute(
        '''SELECT "YayineviID", "YayineviAdi" FROM "YayınEvleri"
           WHERE "YayineviID" = ?''', (yayinevi_id,)
    ))
    if not yazar or not yayinevi:
        return "Listeden geçerli bir yazar ve yayınevi seçin."

    ad_soyad = f"{yazar[0]['YazarAdi']} {yazar[0]['YazarSoyadi']}".strip()
    _, hata = kaydet_veya_hata(
        db,
        '''INSERT INTO "Kitaplar"
           ("KitapAdi", "KitapBasimYili", "KitapYazarAdi",
            "KitapYayinevi", "YazarID", "YayinEviID", "Fiyat")
           VALUES (?, ?, ?, ?, ?, ?, ?)''',
        (kitap_adi, yil, ad_soyad, yayinevi[0]["YayineviAdi"],
         yazar_id, yayinevi_id, fiyat),
    )
    return hata


@app.route("/", methods=["GET", "POST"])
def anasayfa():
    islem = request.form.get("islem", "") if request.method == "POST" else ""
    hata_kitap = None
    hata_yazar = None
    form_kitap = request.form if islem == "kitap" else {
        "yazar_id": request.args.get("yazar_id", "")
    }
    form_yazar = request.form if islem == "yazar" else {}
    db = baglanti_ac()
    try:
        if islem == "yazar":
            yeni_id, hata_yazar = yeni_yazar_kaydet(db, request.form)
            if not hata_yazar:
                return redirect(url_for("anasayfa", eklendi="yazar", yazar_id=yeni_id))
        elif islem == "kitap":
            hata_kitap = yeni_kitap_kaydet(db, request.form)
            if not hata_kitap:
                return redirect(url_for("anasayfa", eklendi="kitap"))

        yazarlar = sozluk_kayitlar(db.execute(
            '''SELECT "YazarID", "YazarAdi", "YazarSoyadi" FROM "Yazarlar"
               ORDER BY "YazarAdi", "YazarSoyadi"'''
        ))
        yayinevleri = sozluk_kayitlar(db.execute(
            '''SELECT "YayineviID", "YayineviAdi" FROM "YayınEvleri"
               ORDER BY "YayineviAdi"'''
        ))

        tablolar = {}
        for tablo in ("Kitaplar", "Yazarlar", "YayınEvleri"):
            sutunlar = db.execute(f'PRAGMA table_info("{tablo}")').fetchall()
            kayitlar = db.execute(f'SELECT * FROM "{tablo}"').fetchall()
            tablolar[tablo] = {
                "sutunlar": [sutun[1] for sutun in sutunlar],
                "veriler": [list(satir) for satir in kayitlar],
            }

        return render_template(
            "index.html",
            tablolar=tablolar, yazarlar=yazarlar, yayinevleri=yayinevleri,
            hata_kitap=hata_kitap, hata_yazar=hata_yazar,
            form_kitap=form_kitap, form_yazar=form_yazar,
            basarili=request.args.get("eklendi", ""),
            max_yil=date.today().year + 1,
        )
    finally:
        db.close()


if __name__ == "__main__":
    app.run(debug=True)
