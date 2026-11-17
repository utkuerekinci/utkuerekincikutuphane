"""Turso / SQLite uyumlu, parametreli sorgularla kütüphane veri katmanı."""
from pathlib import Path
import os
import sqlite3

YEREL_DB = Path(__file__).resolve().parent / "utkuerekincikutuphane.db"
KATEGORILER = [
    "Veri Tabanı ve Yazılım", "Bilgi ve Belge Yönetimi", "Türk Edebiyatı",
    "Dünya Edebiyatı", "Tarih", "Felsefe ve Sosyoloji",
    "Bilim ve Teknoloji", "Araştırma Yöntemleri", "Diğer", "Belirtilmedi",
]
DURUMLAR = ("Mevcut", "Ödünçte", "Belirtilmedi")
SAYFA_BASINA = 15
SIRALAMALAR = {
    "yeni": ("Son eklenenler", 'k."KitapID" DESC'),
    "eski": ("İlk eklenenler", 'k."KitapID" ASC'),
    "ad_az": ("Kitap adı (A-Z)", 'k."KitapAdi" COLLATE NOCASE ASC'),
    "yazar_az": ("Yazar adı (A-Z)", 'k."KitapYazarAdi" COLLATE NOCASE ASC'),
    "yil_yeni": ("Yayın yılı (yeniden eskiye)", 'k."KitapBasimYili" DESC, k."KitapID" DESC'),
    "yil_eski": ("Yayın yılı (eskiden yeniye)", 'k."KitapBasimYili" ASC, k."KitapID" ASC'),
    "fiyat_art": ("Fiyat (artan)", 'k."Fiyat" ASC, k."KitapID" DESC'),
    "fiyat_az": ("Fiyat (azalan)", 'k."Fiyat" DESC, k."KitapID" DESC'),
}


def baglan():
    """Vercel'de yalnızca Turso; yerel bilgisayarda SQLite kullanır."""
    url = (os.environ.get("TURSO_DATABASE_URL") or "").strip()
    token = (os.environ.get("TURSO_AUTH_TOKEN") or "").strip()
    if url and token:
        import libsql
        return libsql.connect(database=url, auth_token=token)
    if url or token or os.environ.get("VERCEL"):
        raise RuntimeError("Turso bağlantı değişkenleri eksik veya hatalı.")
    if not YEREL_DB.is_file():
        raise FileNotFoundError("Yerel veritabanı dosyası bulunamadı.")
    conn = sqlite3.connect(str(YEREL_DB), timeout=15)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def satirlar(cursor):
    """sqlite3.Row gerektirmeden, libsql ve sqlite3 sonuçlarını dict'e çevirir."""
    basliklar = [kolon[0] for kolon in cursor.description]
    return [dict(zip(basliklar, satir)) for satir in cursor.fetchall()]


def tek(db, sql, parametreler=()):
    kayitlar = satirlar(db.execute(sql, tuple(parametreler)))
    return kayitlar[0] if kayitlar else None


def liste(db, sql, parametreler=()):
    return satirlar(db.execute(sql, tuple(parametreler)))


def yazarlar(db):
    return liste(db, '''SELECT "YazarID", "YazarAdi", "YazarSoyadi", "YazarDT", "YazarOT"
                        FROM "Yazarlar" ORDER BY "YazarAdi" COLLATE NOCASE, "YazarSoyadi" COLLATE NOCASE''')


def yayinevleri(db):
    return liste(db, '''SELECT "YayineviID", "YayineviAdi", "YayineviKY", "YayineviURL", "YayineviSehir"
                        FROM "YayınEvleri" ORDER BY "YayineviAdi" COLLATE NOCASE''')


def kitap(db, kitap_id):
    return tek(db, 'SELECT * FROM "Kitaplar" WHERE "KitapID" = ?', (kitap_id,))


def katalog(db, q="", kategori="", durum="", sirala="yeni", sayfa=1):
    """İstatistik, filtre, sayfalama ve SQL injection'a karşı güvenli sıralama."""
    koşullar, p = [], []
    q = q.strip()[:100]
    if q:
        koşullar.append('''(k."KitapAdi" LIKE ? OR k."KitapYazarAdi" LIKE ? OR
          k."KitapYayinevi" LIKE ? OR COALESCE(k."ISBN", '') LIKE ? OR
          COALESCE(k."RafKodu", '') LIKE ?)''')
        p.extend([f"%{q}%"] * 5)
    if kategori:
        koşullar.append('k."Kategori" = ?')
        p.append(kategori)
    if durum in DURUMLAR:
        koşullar.append('k."Durum" = ?')
        p.append(durum)
    where = "WHERE " + " AND ".join(koşullar) if koşullar else ""
    toplam = tek(db, 'SELECT COUNT(*) AS sayi FROM "Kitaplar" k ' + where, p)["sayi"]
    istatistik = tek(db, '''SELECT COUNT(*) AS toplam,
          SUM(CASE WHEN "Durum"='Mevcut' THEN 1 ELSE 0 END) AS mevcut,
          SUM(CASE WHEN "Durum"='Ödünçte' THEN 1 ELSE 0 END) AS odunc,
          SUM(CASE WHEN "Durum"='Belirtilmedi' THEN 1 ELSE 0 END) AS belirsiz,
          COUNT(DISTINCT "Kategori") AS kategori_sayisi
          FROM "Kitaplar"''')
    toplam_sayfa = max(1, (toplam + SAYFA_BASINA - 1) // SAYFA_BASINA)
    sayfa = min(max(1, sayfa), toplam_sayfa)
    order = SIRALAMALAR.get(sirala, SIRALAMALAR["yeni"])[1]
    rows = liste(db, f'''SELECT k.* FROM "Kitaplar" k {where}
        ORDER BY {order} LIMIT ? OFFSET ?''', p + [SAYFA_BASINA, (sayfa - 1) * SAYFA_BASINA])
    return rows, toplam, istatistik, sayfa, toplam_sayfa



def rastgele_kitap(db, haric_id=None):
    """Rastgele bir kitap döndürür; raftaki kitaplara öncelik verir.

    Önce Mevcut, yoksa Belirtilmedi, son çare Ödünçte kitapları dener.
    Yeni öneri istenirse önceki kitap mümkün olduğunca tekrarlanmaz.
    SQL yalnızca SELECT yapar; Turso/SQLite verilerini değiştirmez.
    """
    # Önce "önceki kitap hariç" bütün durumları dene; başka kitap varsa
    # peş peşe aynı kitabı gösterme. Rafta mevcut olana öncelik ver.
    for onceki_haric in ((True, False) if haric_id is not None else (False,)):
        for durum in ("Mevcut", "Belirtilmedi", "Ödünçte"):
            sql = "SELECT * FROM \"Kitaplar\" WHERE COALESCE(\"Durum\", 'Belirtilmedi') = ?"
            params = [durum]
            if onceki_haric:
                sql += ' AND "KitapID" <> ?'
                params.append(haric_id)
            sql += ' ORDER BY RANDOM() LIMIT 1'
            sonuc = tek(db, sql, params)
            if sonuc:
                return sonuc
    return None


def isbn_kullaniliyor(db, isbn, haric_id=None):
    if not isbn:
        return False
    if haric_id is None:
        row = tek(db, '''SELECT COUNT(*) AS n FROM "Kitaplar" WHERE "ISBN" = ?''', (isbn,))
    else:
        row = tek(db, '''SELECT COUNT(*) AS n FROM "Kitaplar" WHERE "ISBN" = ? AND "KitapID" <> ?''', (isbn, haric_id))
    return bool(row["n"])


def kitap_kaydet(db, veri, kitap_id=None):
    """Form doğrulaması app.py içinde; burada yalnızca parametreli SQL yazımı var."""
    yazar = tek(db, 'SELECT "YazarAdi", "YazarSoyadi" FROM "Yazarlar" WHERE "YazarID"=?', (veri["YazarID"],))
    yayinevi = tek(db, 'SELECT "YayineviAdi" FROM "YayınEvleri" WHERE "YayineviID"=?', (veri["YayinEviID"],))
    if not yazar or not yayinevi:
        raise ValueError("Geçerli bir yazar ve yayınevi seçin.")
    gorunen_yazar = veri.get("KitapYazarAdi") or (yazar["YazarAdi"] + " " + yazar["YazarSoyadi"]).strip()
    if kitap_id is not None:
        eski = kitap(db, kitap_id)
        # Yazar ID değişirken eski yazar metni aynen bırakılmışsa görünümü yeni yazara eşitle.
        # Çok yazarlı eski kaydın metnine, yazar ID değişmediyse dokunma.
        if (eski and eski["YazarID"] != veri["YazarID"]
                and gorunen_yazar == (eski.get("KitapYazarAdi") or "")):
            gorunen_yazar = (yazar["YazarAdi"] + " " + yazar["YazarSoyadi"]).strip()
    alanlar = ["KitapAdi", "KitapBasimYili", "KitapYazarAdi", "KitapYayinevi",
              "YazarID", "YayinEviID", "Fiyat", "ISBN", "Kategori", "RafKodu", "Durum"]
    degerler = [veri["KitapAdi"], veri["KitapBasimYili"], gorunen_yazar, yayinevi["YayineviAdi"],
                veri["YazarID"], veri["YayinEviID"], veri["Fiyat"],
                veri["ISBN"], veri["Kategori"], veri["RafKodu"], veri["Durum"]]
    if kitap_id is None:
        sql = 'INSERT INTO "Kitaplar" (' + ','.join('"'+a+'"' for a in alanlar) + ') VALUES (' + ','.join('?' for _ in alanlar) + ')'
        db.execute(sql, degerler)
    else:
        sql = 'UPDATE "Kitaplar" SET ' + ','.join('"'+a+'"=?' for a in alanlar) + ' WHERE "KitapID"=?'
        db.execute(sql, degerler + [kitap_id])
    db.commit()


def yazar_ekle(db, veri):
    result = db.execute('''INSERT INTO "Yazarlar" ("YazarAdi", "YazarSoyadi", "YazarDT", "YazarOT") VALUES (?, ?, ?, ?)''',
                        (veri["YazarAdi"], veri["YazarSoyadi"], veri["YazarDT"], veri["YazarOT"]))
    db.commit()
    return getattr(result, "lastrowid", None)


def yayinevi_ekle(db, veri):
    result = db.execute('''INSERT INTO "YayınEvleri" ("YayineviAdi", "YayineviKY", "YayineviURL", "YayineviSehir") VALUES (?, ?, ?, ?)''',
                        (veri["YayineviAdi"], veri["YayineviKY"], veri["YayineviURL"], veri["YayineviSehir"]))
    db.commit()
    return getattr(result, "lastrowid", None)
