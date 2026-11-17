"""Utku Erekinci Kütüphanesi — herkese açık Flask / Turso CRUD katalog.

Tüm ziyaretçiler kitap ekleyebilir, düzenleyebilir, silebilir ve durumunu değiştirebilir;
yazar ve yayınevi ekleyebilir. Yönetici hesabı / giriş gerekmiyor.
FLASK_SECRET_KEY formların CSRF doğrulaması için Vercel'de sabit olmalıdır.
"""
from datetime import date
import os
import re
import secrets

from flask import Flask, abort, flash, g, redirect, render_template, request, session, url_for
from veritabani import (KATEGORILER, DURUMLAR, SIRALAMALAR, baglan, katalog,
                        kitap, kitap_kaydet, isbn_kullaniliyor, liste, tek,
                        yazarlar, yayinevleri, yazar_ekle, yayinevi_ekle, rastgele_kitap)

app = Flask(__name__)
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")
if os.environ.get("VERCEL"):
    app.config["SESSION_COOKIE_SECURE"] = True
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or secrets.token_hex(32)


def db_getir():
    if "db" not in g:
        g.db = baglan()
    return g.db


@app.teardown_appcontext
def db_kapat(hata=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


@app.context_processor
def ortak_veriler():
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return dict(csrf=session["csrf"])


@app.before_request
def csrf_kontrol():
    if request.method == "POST":
        expected = session.get("csrf", "")
        supplied = request.form.get("csrf", "")
        if not expected or not secrets.compare_digest(expected, supplied):
            abort(400, description="Güvenlik doğrulaması başarısız. Sayfayı yenileyip tekrar deneyin.")


def hata_geri_al(db, ex):
    app.logger.exception("Veritabanı işlemi başarısız")
    try:
        db.rollback()
    except Exception:
        pass  # Bazı libsql bağlantılarında rollback sağlanmayabilir.
    if isinstance(ex, ValueError):
        flash(str(ex), "error")
    else:
        flash("Kayıt işlemi tamamlanamadı. Vercel Logs bölümüne bakın.", "error")


@app.get("/")
def anasayfa():
    q = request.args.get("q", "").strip()
    kategori = request.args.get("kategori", "").strip()
    durum = request.args.get("durum", "").strip()
    sirala = request.args.get("sirala", "yeni")
    try:
        sayfa = int(request.args.get("sayfa", 1))
    except (TypeError, ValueError):
        sayfa = 1
    sayfa = max(1, min(sayfa, 100000))
    db = db_getir()
    kitaplar, filtre_sayisi, istatistik, sayfa, toplam_sayfa = katalog(
        db, q=q, kategori=kategori, durum=durum, sirala=sirala, sayfa=sayfa
    )
    kategoriler = [r["Kategori"] for r in liste(db,
        'SELECT DISTINCT "Kategori" FROM "Kitaplar" WHERE "Kategori" IS NOT NULL ORDER BY "Kategori" COLLATE NOCASE')]
    return render_template(
        "index.html", kitaplar=kitaplar, yazarlar=yazarlar(db), yayinevleri=yayinevleri(db),
        istatistik=istatistik, filtre_sayisi=filtre_sayisi,
        kategoriler=kategoriler, siralama_secenekleri=SIRALAMALAR,
        q=q, kategori=kategori, durum=durum, sirala=sirala,
        sayfa=sayfa, toplam_sayfa=toplam_sayfa,
    )



@app.get("/bugun-ne-okusam")
def bugun_ne_okusam():
    """Herkese açık, veritabanını değiştirmeyen kitap önerisi."""
    db = db_getir()
    onceki = request.args.get("onceki", type=int)
    oneri = rastgele_kitap(db, haric_id=onceki)
    response = app.make_response(render_template("oner.html", kitap=oneri))
    # Rastgele sonucun tarayıcı/ara katman önbelleğinden dönmesini önler.
    response.headers["Cache-Control"] = "no-store, max-age=0"
    return response


def kitap_form_verisi(form):
    """Yalnızca izin verilen alanları alır; hatalı değeri formda korur."""
    kitap_adi = form.get("KitapAdi", "").strip()
    isbn = form.get("ISBN", "").strip().replace(" ", "")
    raf = form.get("RafKodu", "").strip()
    kategori = form.get("Kategori", "").strip()
    durum = form.get("Durum", "Mevcut").strip()
    yazar_adi = form.get("KitapYazarAdi", "").strip()
    hatalar = []
    if not kitap_adi or len(kitap_adi) > 200:
        hatalar.append("Kitap adı zorunlu ve en fazla 200 karakter olabilir.")
    if isbn and (len(isbn) > 25 or not re.fullmatch(r"[0-9Xx-]+", isbn)):
        hatalar.append("ISBN yalnızca rakam, X ve tire içerebilir (en fazla 25 karakter).")
    if len(raf) > 60 or len(yazar_adi) > 250:
        hatalar.append("Raf veya yazar görünen ad alanı çok uzun.")
    if kategori not in KATEGORILER:
        hatalar.append("Listeden bir kategori seçin.")
    if durum not in DURUMLAR:
        hatalar.append("Geçerli bir ödünç durumu seçin.")
    try:
        yil = int(form.get("KitapBasimYili", ""))
        fiyat = int(form.get("Fiyat", ""))
        yazar_id = int(form.get("YazarID", ""))
        yayinevi_id = int(form.get("YayinEviID", ""))
        if not 1400 <= yil <= date.today().year + 1:
            hatalar.append("Basım yılı 1400 ile gelecek yıl arasında olmalıdır.")
        if not 0 <= fiyat <= 100000000:
            hatalar.append("Fiyat 0 ile 100 milyon TL arasında olmalıdır.")
        if yazar_id <= 0 or yayinevi_id <= 0:
            hatalar.append("Geçerli bir yazar ve yayınevi seçin.")
    except ValueError:
        yil = fiyat = yazar_id = yayinevi_id = None
        hatalar.append("Yıl, fiyat, yazar ve yayınevi alanlarını kontrol edin.")
    return dict(KitapAdi=kitap_adi, ISBN=isbn or None, RafKodu=raf or None,
                Kategori=kategori, Durum=durum, KitapYazarAdi=yazar_adi,
                KitapBasimYili=yil, Fiyat=fiyat, YazarID=yazar_id,
                YayinEviID=yayinevi_id), hatalar


def form_goster(islem, degerler=None, kitap_id=None):
    db = db_getir()
    return render_template("kitap_form.html", islem=islem, kitap=degerler or {},
                           kitap_id=kitap_id, yazarlar=yazarlar(db), yayinevleri=yayinevleri(db),
                           kategoriler=KATEGORILER, durumlar=DURUMLAR,
                           max_yil=date.today().year + 1)


@app.route("/kitap/ekle", methods=["GET", "POST"])
def kitap_ekle():
    if request.method == "GET":
        return form_goster("ekle", {"Durum": "Mevcut", "Kategori": "Belirtilmedi"})
    veri, hatalar = kitap_form_verisi(request.form)
    db = db_getir()
    if not hatalar and isbn_kullaniliyor(db, veri["ISBN"]):
        hatalar.append("Bu ISBN zaten kayıtlı.")
    if not hatalar:
        try:
            kitap_kaydet(db, veri)
            flash("Kitap başarıyla eklendi.", "success")
            return redirect(url_for("anasayfa"))
        except Exception as ex:
            hata_geri_al(db, ex)
    else:
        for hata in hatalar:
            flash(hata, "error")
    return form_goster("ekle", request.form)


@app.route("/kitap/<int:kitap_id>/duzenle", methods=["GET", "POST"])
def kitap_duzenle(kitap_id):
    db = db_getir()
    mevcut = kitap(db, kitap_id)
    if not mevcut:
        abort(404)
    if request.method == "GET":
        return form_goster("duzenle", mevcut, kitap_id)
    veri, hatalar = kitap_form_verisi(request.form)
    if not hatalar and isbn_kullaniliyor(db, veri["ISBN"], kitap_id):
        hatalar.append("Bu ISBN başka bir kitapta kullanılıyor.")
    if not hatalar:
        try:
            kitap_kaydet(db, veri, kitap_id)
            flash("Kitap bilgileri güncellendi.", "success")
            return redirect(url_for("anasayfa"))
        except Exception as ex:
            hata_geri_al(db, ex)
    else:
        for hata in hatalar:
            flash(hata, "error")
    return form_goster("duzenle", request.form, kitap_id)


@app.post("/kitap/<int:kitap_id>/durum")
def durum_degistir(kitap_id):
    db = db_getir()
    mevcut = kitap(db, kitap_id)
    if not mevcut:
        abort(404)
    yeni = "Ödünçte" if mevcut["Durum"] == "Mevcut" else "Mevcut"
    try:
        db.execute('UPDATE "Kitaplar" SET "Durum"=? WHERE "KitapID"=?', (yeni, kitap_id))
        db.commit()
        flash(f"Kitap durumu: {yeni}.", "success")
    except Exception as ex:
        hata_geri_al(db, ex)
    return redirect(url_for("anasayfa"))


@app.post("/kitap/<int:kitap_id>/sil")
def kitap_sil(kitap_id):
    db = db_getir()
    mevcut = kitap(db, kitap_id)
    if not mevcut:
        abort(404)
    try:
        db.execute('DELETE FROM "Kitaplar" WHERE "KitapID"=?', (kitap_id,))
        db.commit()
        flash(f"'{mevcut['KitapAdi']}' kaydı silindi.", "success")
    except Exception as ex:
        hata_geri_al(db, ex)
    return redirect(url_for("anasayfa"))


@app.post("/yazar/ekle")
def yazar_kaydet():
    ad = request.form.get("ad", "").strip()
    soyad = request.form.get("soyad", "").strip()
    dogum = request.form.get("dogum", "").strip()
    olum = request.form.get("olum", "").strip()
    if not ad or not soyad or len(ad) > 100 or len(soyad) > 100:
        flash("Yazar adı ve soyadı zorunlu; en fazla 100 karakter.", "error")
        return redirect(url_for("anasayfa") + "#yazarlar")
    from datetime import date as dt
    try:
        d = dt.fromisoformat(dogum) if dogum else None
        o = dt.fromisoformat(olum) if olum else None
        if d and o and o < d:
            raise ValueError()
    except ValueError:
        flash("Tarihleri kontrol edin; ölüm tarihi doğumdan önce olamaz.", "error")
        return redirect(url_for("anasayfa") + "#yazarlar")
    db = db_getir()
    ayni = tek(db, '''SELECT COUNT(*) AS n FROM "Yazarlar" WHERE LOWER("YazarAdi")=LOWER(?)
                      AND LOWER("YazarSoyadi")=LOWER(?)''', (ad, soyad))
    if ayni["n"]:
        flash("Bu isim ve soyadla bir yazar zaten var.", "error")
        return redirect(url_for("anasayfa") + "#yazarlar")
    try:
        yazar_ekle(db, {"YazarAdi": ad, "YazarSoyadi": soyad, "YazarDT": dogum or None, "YazarOT": olum or None})
        flash("Yeni yazar kaydedildi; kitap eklerken listeden seçebilirsiniz.", "success")
    except Exception as ex:
        hata_geri_al(db, ex)
    return redirect(url_for("anasayfa") + "#yazarlar")


@app.post("/yayinevi/ekle")
def yayinevi_kaydet():
    ad = request.form.get("ad", "").strip()
    sehir = request.form.get("sehir", "").strip()
    url = request.form.get("url", "").strip()
    yil_txt = request.form.get("yil", "").strip()
    if not ad or len(ad) > 180 or len(sehir) > 100 or len(url) > 250:
        flash("Yayınevi adını ve alanların uzunluğunu kontrol edin.", "error")
        return redirect(url_for("anasayfa") + "#yayinevleri")
    if url and not (url.startswith("https://") or url.startswith("http://")):
        flash("Yayınevi sitesi http:// veya https:// ile başlamalı.", "error")
        return redirect(url_for("anasayfa") + "#yayinevleri")
    try:
        yil = int(yil_txt) if yil_txt else None
        if yil is not None and not 1400 <= yil <= date.today().year:
            raise ValueError()
    except ValueError:
        flash("Kuruluş yılını kontrol edin.", "error")
        return redirect(url_for("anasayfa") + "#yayinevleri")
    db = db_getir()
    if tek(db, 'SELECT COUNT(*) AS n FROM "YayınEvleri" WHERE LOWER("YayineviAdi")=LOWER(?)', (ad,))["n"]:
        flash("Bu yayınevi zaten kayıtlı.", "error")
        return redirect(url_for("anasayfa") + "#yayinevleri")
    try:
        yayinevi_ekle(db, {"YayineviAdi": ad, "YayineviKY": yil,
                             "YayineviURL": url or None, "YayineviSehir": sehir or None})
        flash("Yeni yayınevi kaydedildi; kitap eklerken listeden seçebilirsiniz.", "success")
    except Exception as ex:
        hata_geri_al(db, ex)
    return redirect(url_for("anasayfa") + "#yayinevleri")


if __name__ == "__main__":
    app.run(debug=not bool(os.environ.get("VERCEL")))
