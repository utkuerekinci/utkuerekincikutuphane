from datetime import date
from pathlib import Path
import os
import shutil
import sqlite3

from flask import Flask, render_template, request, redirect, url_for

app = Flask(__name__)

KLASOR = Path(__file__).resolve().parent
KAYNAK_DB = KLASOR / "utkuerekincikutuphane.db"


def baglanti_ac():
    # Vercel'de proje dosyalari salt okunurdur. Yazmak icin /tmp kullanilir.
    # /tmp verileri kalici DEĞİLDİR; farkli fonksiyon kopyalari paylasmaz.
    if os.environ.get("VERCEL"):
        db_yolu = Path("/tmp/utkuerekincikutuphane.db")
        if not db_yolu.exists():
            shutil.copyfile(KAYNAK_DB, db_yolu)
    else:
        db_yolu = KAYNAK_DB

    baglanti = sqlite3.connect(db_yolu, timeout=10)
    baglanti.row_factory = sqlite3.Row
    return baglanti


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
                    yazar = db.execute(
                        'SELECT YazarID, YazarAdi, YazarSoyadi FROM "Yazarlar" WHERE YazarID = ?',
                        (yazar_id,),
                    ).fetchone()
                    yayinevi = db.execute(
                        'SELECT YayineviID, YayineviAdi FROM "YayınEvleri" WHERE YayineviID = ?',
                        (yayinevi_id,),
                    ).fetchone()

                    if yazar is None or yayinevi is None:
                        hata = "Listeden geçerli bir yazar ve yayınevi seçin."
                    else:
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

        yazarlar = db.execute(
            'SELECT YazarID, YazarAdi, YazarSoyadi FROM "Yazarlar" '
            'ORDER BY YazarAdi, YazarSoyadi'
        ).fetchall()
        yayinevleri = db.execute(
            'SELECT YayineviID, YayineviAdi FROM "YayınEvleri" ORDER BY YayineviAdi'
        ).fetchall()

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
