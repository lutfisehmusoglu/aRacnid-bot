# Discord İsim Doğrulama Botu

Python 3.12 ve `discord.py` ile hazırlanmış, veritabanı ve web sunucusu gerektirmeyen küçük bir doğrulama botudur. Kullanıcı oyun içi adını modal üzerinden girer; bot nickname'i değiştirir, `NoName` rolünü kaldırır ve `R1` rolünü verir.

## Özellikler

- Kalıcı (`persistent`) buton: bot yeniden başladıktan sonra da çalışır.
- Tek panel mesajı: mesaj ID'si otomatik oluşan `state.json` içinde tutulur; dosya yoksa kanal geçmişindeki bot paneli bulunur.
- Nickname doğrulaması: baş/son boşluk temizleme, 2–32 karakter sınırı ve kontrol karakteri denetimi.
- İzin ve rol hiyerarşisi kontrolleri.
- Nickname ve roller tek Discord üye-güncelleme isteğinde değiştirilir; iki ayrı rol çağrısının yarım durum bırakması önlenir.
- Başarılı işlemler log kanalına embed olarak gönderilir.
- Kullanıcı yanıtları yalnızca kullanıcıya görünen ephemeral mesajlardır.
- Carl-bot rol akışına dokunmaz; bu botta `on_member_join` veya otomatik rol verme yoktur.

## Gereksinimler

- Python 3.12
- Discord sunucusunda uygulama ekleme/yönetme yetkisi
- Carl-bot'un yeni üyelere `NoName` rolünü vermesi

Repository'deki `.python-version` dosyası Railway Railpack'e Python 3.12 kullanmasını söyler.

## 1. Discord Developer Portal'da bot oluşturma

1. [Discord Developer Portal](https://discord.com/developers/applications) sayfasını aç.
2. **New Application** seçeneğiyle bir uygulama oluştur.
3. Sol menüden **Bot** sayfasına gir ve **Add Bot** seçeneğini kullan (arayüz otomatik bot oluşturduysa bu adım görünmeyebilir).
4. **Reset Token** ile token üret ve güvenli bir yere kaydet. Token'ı GitHub'a, mesaja veya ekran görüntüsüne koyma.
5. Token daha önce paylaşıldıysa hemen yeniden üret.

## 2. Gerekli intents

Bot yalnızca standart **Guilds** intentini kullanır. **Server Members Intent**, **Presence Intent** ve **Message Content Intent** bu akış için gerekli değildir; Developer Portal'da açma.

Bot yalnızca işlem yapan tek üyeyi REST API ile yeniden okur; tüm üye listesini istemez ve üye gateway olaylarını dinlemez. Bu nedenle Members intent gerekmez. Kod yeni üye katılım olayını da dinlemez.

## 3. Gerekli bot permissions

Yalnızca şu izinleri ver:

- Manage Nicknames
- Manage Roles
- View Channels
- Send Messages
- Embed Links
- Read Message History
- Use Application Commands

**Administrator verme.** `#isim-ayarla` kanalındaki permission overwrite ayarlarının da bot için View Channel, Send Messages, Embed Links ve Read Message History izinlerini engellemediğinden emin ol. Log kanalında View Channel, Send Messages ve Embed Links izinleri açık olmalı.

## 4. Botu sunucuya davet etme

1. Developer Portal'da **OAuth2 > URL Generator** sayfasına gir.
2. Scopes bölümünde `bot` ve `applications.commands` seç.
3. Bot Permissions bölümünde yukarıdaki yedi izni seç.
4. Oluşan URL'yi aç, doğru sunucuyu seç ve botu ekle.

Botun uygulama ayarlarında herkese açık olması gerekmiyorsa **Public Bot** seçeneğini kapalı tutabilirsin.

## 5. Guild, kanal ve rol ID'lerini alma

1. Discord'da **Kullanıcı Ayarları > Gelişmiş > Geliştirici Modu** seçeneğini aç.
2. Sunucu ikonuna sağ tıkla, **Sunucu ID'sini Kopyala**: `GUILD_ID`.
3. `#isim-ayarla` kanalına sağ tıkla, **Kanal ID'sini Kopyala**: `NAME_CHANNEL_ID`.
4. Log kanalına sağ tıkla, **Kanal ID'sini Kopyala**: `LOG_CHANNEL_ID`.
5. **Sunucu Ayarları > Roller** altında `NoName` rolüne sağ tıkla, **Rol ID'sini Kopyala**: `NONAME_ROLE_ID`.
6. Aynı işlemi `R1` için yap: `R1_ROLE_ID`.

## 6. `.env` ile local test

Python 3.12 kurulu bir PowerShell'de proje klasöründe:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

`.env` dosyasını doldur:

```dotenv
DISCORD_TOKEN=bot_token_buraya
GUILD_ID=123456789012345678
NAME_CHANNEL_ID=123456789012345678
NONAME_ROLE_ID=123456789012345678
R1_ROLE_ID=123456789012345678
LOG_CHANNEL_ID=123456789012345678
```

Ardından çalıştır:

```powershell
python main.py
```

Bot ilk çalışmada `#isim-ayarla` kanalına paneli yollar ve `state.json` oluşturur. `state.json` ile `.env` Git tarafından yok sayılır. `state.json` silinse bile bot son 100 kanal mesajını tarayarak kendi panelini bulur.

## 7. GitHub'a gönderme

Yeni bir boş GitHub repository oluştur. Sonra proje klasöründe:

```powershell
git init
git add .
git commit -m "Discord doğrulama botunu ekle"
git branch -M main
git remote add origin https://github.com/KULLANICI/REPOSITORY.git
git push -u origin main
```

`git status` çıktısında `.env` görünmemelidir. Token yanlışlıkla commit edildiyse yalnızca dosyayı silmek yeterli değildir; Discord Developer Portal'dan token'ı hemen yenile.

## 8. Railway'e deploy

1. [Railway](https://railway.com/) üzerinde yeni proje oluştur.
2. **Deploy from GitHub repo** seç ve repository'yi bağla.
3. Railway `requirements.txt` dosyasından Python projesini algılar ve bağımlılıkları kurar.
4. Service **Settings > Deploy > Start Command** alanına `python main.py` yaz.
5. Bu bir worker/background process'tir. Public Networking/domain oluşturma ve web server ekleme.
6. Tek replica kullan. Birden fazla replica aynı Discord botunu eş zamanlı çalıştırmamalıdır.

## 9. Railway Variables

Service içindeki **Variables** sekmesine şu altı değişkeni tek tek ekle:

- `DISCORD_TOKEN`
- `GUILD_ID`
- `NAME_CHANNEL_ID`
- `NONAME_ROLE_ID`
- `R1_ROLE_ID`
- `LOG_CHANNEL_ID`

Değerlerde tırnak veya fazladan boşluk kullanma. Variables kaydedilince servisi yeniden deploy et. Railway'in geçici dosya sistemi nedeniyle deploy sonrasında `state.json` kaybolabilir; bot bu durumda kanal geçmişinden mevcut paneli bulur ve yeni mesaj oluşturmaz.

## 10. Role hierarchy

**Sunucu Ayarları > Roller** ekranında botun rolünü hem `NoName` hem de `R1` rollerinin üstüne taşı. Bot ayrıca doğrulayacağı üyenin en yüksek rolünden de yukarıda olmalıdır. Discord, izin verilmiş olsa bile eşit veya üst roldeki üyelerin nickname ve rollerinin değiştirilmesine izin vermez.

Önerilen sıralama:

```text
Bot rolü
R1
NoName
@everyone
```

## Kullanım ve hata ayıklama

- Carl-bot yeni üyeye `NoName` verir.
- Kullanıcı `#isim-ayarla` kanalındaki **🎮 İsmimi Ayarla** butonuna basar.
- İsim geçerliyse nickname, `NoName` ve `R1` tek işlemde güncellenir.
- Kullanıcıda `NoName` yoksa bot **✅ Zaten doğrulanmışsın.** yanıtını verir.
- Konsol ve Railway deployment logları; eksik izin, yanlış ID, rol hiyerarşisi ve Discord API hatalarını ayrıntılı gösterir.

Panel oluşturulamıyorsa önce ID'leri, kanal permission overwrite ayarlarını ve bot rol sırasını kontrol et.

## Railway start command

```text
python main.py
```
