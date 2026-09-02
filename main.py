from __future__ import annotations

import asyncio
import json
import logging
import os
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import discord
from dotenv import load_dotenv


LOGGER = logging.getLogger("verification_bot")
BASE_DIR = Path(__file__).resolve().parent
STATE_FILE = BASE_DIR / "state.json"
PANEL_TITLE = "🎮 Oyun İçi İsmini Ayarla"
PANEL_MARKER = "verification-bot:name-panel:v1"
BUTTON_CUSTOM_ID = "verification:set-game-name:v1"


class ConfigError(RuntimeError):
    """Raised when required environment configuration is missing or invalid."""


class VerificationError(RuntimeError):
    """An expected error that is safe to show to a Discord user."""


@dataclass(frozen=True, slots=True)
class Config:
    token: str
    guild_id: int
    name_channel_id: int
    noname_role_id: int
    r1_role_id: int
    log_channel_id: int

    @classmethod
    def from_env(cls) -> Config:
        load_dotenv()
        required = (
            "DISCORD_TOKEN",
            "GUILD_ID",
            "NAME_CHANNEL_ID",
            "NONAME_ROLE_ID",
            "R1_ROLE_ID",
            "LOG_CHANNEL_ID",
        )
        missing = [name for name in required if not os.getenv(name, "").strip()]
        if missing:
            raise ConfigError(f"Eksik environment variable(lar): {', '.join(missing)}")

        def snowflake(name: str) -> int:
            raw = os.environ[name].strip()
            try:
                value = int(raw)
            except ValueError as exc:
                raise ConfigError(f"{name} pozitif bir Discord ID olmalıdır.") from exc
            if value <= 0:
                raise ConfigError(f"{name} pozitif bir Discord ID olmalıdır.")
            return value

        return cls(
            token=os.environ["DISCORD_TOKEN"].strip(),
            guild_id=snowflake("GUILD_ID"),
            name_channel_id=snowflake("NAME_CHANNEL_ID"),
            noname_role_id=snowflake("NONAME_ROLE_ID"),
            r1_role_id=snowflake("R1_ROLE_ID"),
            log_channel_id=snowflake("LOG_CHANNEL_ID"),
        )


def panel_embed() -> discord.Embed:
    embed = discord.Embed(
        title=PANEL_TITLE,
        description=(
            "Sunucuya erişmek için aşağıdaki butona bas ve oyun içi adını gir. "
            "Bu ad sunucu takma adın olarak ayarlanacaktır."
        ),
        colour=discord.Colour.blurple(),
    )
    embed.set_footer(text=PANEL_MARKER)
    return embed


def validate_nickname(raw_value: str) -> str:
    nickname = raw_value.strip()
    if not 2 <= len(nickname) <= 32:
        raise VerificationError("Oyun içi adın 2–32 karakter arasında olmalıdır.")
    if any(unicodedata.category(character) in {"Cc", "Cs"} for character in nickname):
        raise VerificationError("Oyun içi adın kontrol karakterleri içeremez.")
    if not any(character.isprintable() and not character.isspace() for character in nickname):
        raise VerificationError("Geçerli bir oyun içi adı girmelisin.")
    return nickname


def load_message_id(config: Config) -> int | None:
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError, TypeError):
        LOGGER.warning("state.json okunamadı; kanal geçmişi taranacak.", exc_info=True)
        return None

    if not isinstance(data, dict):
        LOGGER.warning("state.json bir JSON nesnesi değil; kanal geçmişi taranacak.")
        return None
    if data.get("guild_id") != config.guild_id or data.get("channel_id") != config.name_channel_id:
        return None
    message_id = data.get("message_id")
    return message_id if isinstance(message_id, int) and message_id > 0 else None


def save_message_id(config: Config, message_id: int) -> None:
    data = {
        "guild_id": config.guild_id,
        "channel_id": config.name_channel_id,
        "message_id": message_id,
    }
    temporary_file = STATE_FILE.with_suffix(".json.tmp")
    try:
        temporary_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary_file.replace(STATE_FILE)
    except OSError:
        LOGGER.exception(
            "Doğrulama mesajı ID'si state.json dosyasına yazılamadı. "
            "Sonraki açılışta kanal geçmişi taranacak."
        )


def is_our_panel(message: discord.Message, bot_user_id: int) -> bool:
    if message.author.id != bot_user_id or not message.embeds:
        return False
    embed = message.embeds[0]
    return embed.title == PANEL_TITLE and bool(embed.footer and embed.footer.text == PANEL_MARKER)


class NameModal(discord.ui.Modal, title="Oyun İçi İsmini Ayarla"):
    game_name = discord.ui.TextInput(
        label="Oyun içi adın",
        placeholder="Oyun içi adını yaz",
        required=True,
        min_length=2,
        max_length=32,
        style=discord.TextStyle.short,
    )

    def __init__(self, bot: VerificationBot) -> None:
        super().__init__(custom_id="verification:name-modal:v1", timeout=300)
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            nickname = validate_nickname(str(self.game_name.value))
        except VerificationError as exc:
            await interaction.response.send_message(f"❌ {exc}", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        await self.bot.verify_member(interaction, nickname)

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        LOGGER.error(
            "Modal işlenirken beklenmeyen hata oluştu.",
            exc_info=(type(error), error, error.__traceback__),
        )
        await self.bot.send_interaction_error(
            interaction, "Beklenmeyen bir hata oluştu. Lütfen daha sonra tekrar dene."
        )


class VerificationView(discord.ui.View):
    def __init__(self, bot: VerificationBot) -> None:
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(
        label="🎮 İsmimi Ayarla",
        style=discord.ButtonStyle.primary,
        custom_id=BUTTON_CUSTOM_ID,
    )
    async def set_name(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if interaction.guild_id != self.bot.config.guild_id:
            await interaction.response.send_message(
                "❌ Bu doğrulama paneli bu sunucu için yapılandırılmamış.", ephemeral=True
            )
            return
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "❌ Üyelik bilgilerin alınamadı. Lütfen tekrar dene.", ephemeral=True
            )
            return

        noname_role = interaction.guild.get_role(self.bot.config.noname_role_id)
        if noname_role is None:
            LOGGER.error("NoName rolü bulunamadı: %s", self.bot.config.noname_role_id)
            await interaction.response.send_message(
                "❌ Doğrulama rolü bulunamadı. Lütfen bir yetkiliye haber ver.", ephemeral=True
            )
            return
        if noname_role not in interaction.user.roles:
            await interaction.response.send_message("✅ Zaten doğrulanmışsın.", ephemeral=True)
            return

        await interaction.response.send_modal(NameModal(self.bot))

    async def on_error(
        self,
        interaction: discord.Interaction,
        error: Exception,
        item: discord.ui.Item[discord.ui.View],
    ) -> None:
        LOGGER.error(
            "Buton işlenirken beklenmeyen hata oluştu.",
            exc_info=(type(error), error, error.__traceback__),
        )
        await self.bot.send_interaction_error(
            interaction, "Beklenmeyen bir hata oluştu. Lütfen daha sonra tekrar dene."
        )


class VerificationBot(discord.Client):
    def __init__(self, config: Config) -> None:
        intents = discord.Intents.none()
        intents.guilds = True
        super().__init__(intents=intents, allowed_mentions=discord.AllowedMentions.none())
        self.config = config
        self.verification_view = VerificationView(self)
        self._panel_lock = asyncio.Lock()
        self._panel_ready = False
        self._member_locks: dict[int, asyncio.Lock] = {}

    async def setup_hook(self) -> None:
        self.add_view(self.verification_view)

    async def on_ready(self) -> None:
        if self.user is None:
            return
        LOGGER.info("Discord'a bağlanıldı: %s (ID: %s)", self.user, self.user.id)
        try:
            await self.ensure_verification_panel()
        except Exception:
            LOGGER.exception("Doğrulama paneli hazırlanamadı.")

    async def ensure_verification_panel(self) -> None:
        async with self._panel_lock:
            if self._panel_ready:
                return
            if self.user is None:
                raise RuntimeError("Bot kullanıcısı henüz hazır değil.")

            guild = self.get_guild(self.config.guild_id)
            if guild is None:
                raise RuntimeError(
                    f"GUILD_ID ile belirtilen sunucu bulunamadı: {self.config.guild_id}"
                )
            channel = guild.get_channel(self.config.name_channel_id)
            if not isinstance(channel, discord.TextChannel):
                raise RuntimeError(
                    "NAME_CHANNEL_ID bu sunucuda erişilebilir bir metin kanalını göstermiyor."
                )

            me = guild.me
            permissions = channel.permissions_for(me)
            missing_permissions = [
                label
                for allowed, label in (
                    (permissions.view_channel, "View Channel"),
                    (permissions.send_messages, "Send Messages"),
                    (permissions.embed_links, "Embed Links"),
                    (permissions.read_message_history, "Read Message History"),
                )
                if not allowed
            ]
            if missing_permissions:
                raise RuntimeError(
                    f"#{channel.name} kanalında eksik izinler: {', '.join(missing_permissions)}"
                )

            message: discord.Message | None = None
            saved_message_id = load_message_id(self.config)
            if saved_message_id is not None:
                try:
                    candidate = await channel.fetch_message(saved_message_id)
                    if is_our_panel(candidate, self.user.id):
                        message = candidate
                    else:
                        LOGGER.warning("state.json içindeki mesaj doğrulama paneli değil; geçmiş taranacak.")
                except discord.NotFound:
                    LOGGER.info("Kaydedilmiş doğrulama mesajı bulunamadı; geçmiş taranacak.")

            if message is None:
                async for candidate in channel.history(limit=100):
                    if is_our_panel(candidate, self.user.id):
                        message = candidate
                        break

            if message is None:
                message = await channel.send(embed=panel_embed(), view=self.verification_view)
                LOGGER.info("Doğrulama paneli oluşturuldu: mesaj ID %s", message.id)
            else:
                await message.edit(embed=panel_embed(), view=self.verification_view)
                LOGGER.info("Mevcut doğrulama paneli kullanılıyor: mesaj ID %s", message.id)

            save_message_id(self.config, message.id)
            self._panel_ready = True

    def _member_lock(self, member_id: int) -> asyncio.Lock:
        lock = self._member_locks.get(member_id)
        if lock is None:
            lock = asyncio.Lock()
            self._member_locks[member_id] = lock
        return lock

    async def verify_member(self, interaction: discord.Interaction, nickname: str) -> None:
        try:
            if (
                interaction.guild_id != self.config.guild_id
                or interaction.guild is None
                or not isinstance(interaction.user, discord.Member)
            ):
                raise VerificationError("Üyelik bilgilerin alınamadı. Lütfen tekrar dene.")

            async with self._member_lock(interaction.user.id):
                guild = interaction.guild
                try:
                    member = await guild.fetch_member(interaction.user.id)
                except discord.NotFound as exc:
                    raise VerificationError("Artık bu sunucunun bir üyesi değilsin.") from exc
                except discord.HTTPException as exc:
                    LOGGER.error(
                        "Güncel üye bilgisi alınamadı. member_id=%s, status=%s, code=%s",
                        interaction.user.id,
                        exc.status,
                        exc.code,
                    )
                    raise VerificationError(
                        "Üyelik bilgilerin şu anda alınamadı. Lütfen biraz sonra tekrar dene."
                    ) from exc

                noname_role = guild.get_role(self.config.noname_role_id)
                r1_role = guild.get_role(self.config.r1_role_id)
                if noname_role is None or r1_role is None:
                    missing = "NoName" if noname_role is None else "R1"
                    LOGGER.error("%s rolü bulunamadı. Guild ID: %s", missing, guild.id)
                    raise VerificationError(
                        f"{missing} rolü bulunamadı. Lütfen bir yetkiliye haber ver."
                    )

                if noname_role not in member.roles:
                    await interaction.edit_original_response(content="✅ Zaten doğrulanmışsın.")
                    return

                me = guild.me
                if member.id == guild.owner_id:
                    raise VerificationError("Sunucu sahibinin nickname veya rolleri bot tarafından değiştirilemez.")
                if member.top_role >= me.top_role:
                    LOGGER.warning(
                        "Hiyerarşi nedeniyle üye değiştirilemedi. member=%s (%s), member_role=%s, bot_role=%s",
                        member,
                        member.id,
                        member.top_role,
                        me.top_role,
                    )
                    raise VerificationError(
                        "Rol hiyerarşisi yetersiz: bot rolü senin en yüksek rolünün üstünde olmalı."
                    )
                if not me.guild_permissions.manage_nicknames:
                    raise VerificationError("Botta Manage Nicknames izni eksik. Lütfen bir yetkiliye haber ver.")
                if not me.guild_permissions.manage_roles:
                    raise VerificationError("Botta Manage Roles izni eksik. Lütfen bir yetkiliye haber ver.")

                for role, label in ((noname_role, "NoName"), (r1_role, "R1")):
                    if role.managed:
                        raise VerificationError(f"{label} rolü bir entegrasyon tarafından yönetiliyor.")
                    if role >= me.top_role:
                        LOGGER.warning(
                            "Rol hiyerarşisi yetersiz. target_role=%s (%s), bot_role=%s",
                            role,
                            role.id,
                            me.top_role,
                        )
                        raise VerificationError(
                            f"Rol hiyerarşisi yetersiz: bot rolü {label} rolünün üstünde olmalı."
                        )

                old_nickname = member.nick
                desired_roles = [
                    role
                    for role in member.roles
                    if not role.is_default() and role.id != noname_role.id
                ]
                if r1_role not in desired_roles:
                    desired_roles.append(r1_role)

                reason = f"İsim doğrulama: {member} ({member.id})"
                try:
                    updated_member = await member.edit(
                        nick=nickname,
                        roles=desired_roles,
                        reason=reason,
                    )
                except discord.Forbidden as exc:
                    LOGGER.warning(
                        "Discord işlemi reddetti. member=%s (%s), status=%s",
                        member,
                        member.id,
                        exc.status,
                    )
                    raise VerificationError(
                        "Discord işlemi reddetti. Bot izinlerini ve rol hiyerarşisini kontrol et."
                    ) from exc
                except discord.HTTPException as exc:
                    LOGGER.error(
                        "Üye doğrulama isteği başarısız. member=%s (%s), status=%s, code=%s",
                        member,
                        member.id,
                        exc.status,
                        exc.code,
                    )
                    if exc.status == 400:
                        raise VerificationError(
                            "Bu isim Discord nickname kurallarına uygun değil. Başka bir isim dene."
                        ) from exc
                    raise VerificationError(
                        "Discord işlemi şu anda tamamlanamadı. Lütfen biraz sonra tekrar dene."
                    ) from exc

                if updated_member is None:
                    LOGGER.critical("Discord güncellenmiş üyeyi döndürmedi. member_id=%s", member.id)
                    raise VerificationError(
                        "Doğrulama sonucu doğrulanamadı. Lütfen bir yetkiliye haber ver."
                    )
                updated_role_ids = {role.id for role in updated_member.roles}
                if (
                    updated_member.nick != nickname
                    or noname_role.id in updated_role_ids
                    or r1_role.id not in updated_role_ids
                ):
                    LOGGER.critical(
                        "Discord beklenmeyen üye durumu döndürdü. member=%s (%s)", member, member.id
                    )
                    raise VerificationError(
                        "Doğrulama sonucu doğrulanamadı. Lütfen bir yetkiliye haber ver."
                    )

                LOGGER.info(
                    "Doğrulama başarılı. member=%s (%s), old_nick=%r, new_nick=%r",
                    member,
                    member.id,
                    old_nickname,
                    nickname,
                )
                await self.send_success_log(updated_member, old_nickname, nickname)
                await interaction.edit_original_response(
                    content="✅ İsmin ayarlandı. Sunucuya erişimin açıldı."
                )
        except VerificationError as exc:
            await self.send_interaction_error(interaction, str(exc))
        except Exception:
            LOGGER.exception("Üye doğrulanırken beklenmeyen hata oluştu.")
            await self.send_interaction_error(
                interaction, "Beklenmeyen bir hata oluştu. Lütfen daha sonra tekrar dene."
            )

    async def send_success_log(
        self,
        member: discord.Member,
        old_nickname: str | None,
        new_nickname: str,
    ) -> None:
        channel = member.guild.get_channel(self.config.log_channel_id)
        if not isinstance(channel, discord.TextChannel):
            LOGGER.error("Log kanalı bulunamadı: %s", self.config.log_channel_id)
            return

        embed = discord.Embed(
            title="✅ Kullanıcı Doğrulandı",
            colour=discord.Colour.green(),
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(name="Discord kullanıcı adı", value=str(member), inline=False)
        embed.add_field(name="Kullanıcı", value=member.mention, inline=False)
        embed.add_field(name="User ID", value=str(member.id), inline=False)
        embed.add_field(name="Eski nickname", value=old_nickname or "Yok", inline=False)
        embed.add_field(name="Yeni nickname", value=new_nickname, inline=False)
        embed.add_field(name="İşlem tarihi", value=discord.utils.format_dt(embed.timestamp, "F"), inline=False)

        try:
            await channel.send(embed=embed)
        except (discord.Forbidden, discord.HTTPException):
            LOGGER.exception("Başarılı doğrulama log kanalına gönderilemedi. member_id=%s", member.id)

    async def send_interaction_error(self, interaction: discord.Interaction, message: str) -> None:
        content = f"❌ {message}"
        try:
            if interaction.response.is_done():
                await interaction.edit_original_response(content=content)
            else:
                await interaction.response.send_message(content, ephemeral=True)
        except (discord.NotFound, discord.HTTPException):
            LOGGER.exception("Ephemeral hata mesajı kullanıcıya gönderilemedi.")


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def main() -> None:
    configure_logging()
    try:
        config = Config.from_env()
    except ConfigError as exc:
        LOGGER.critical("Yapılandırma hatası: %s", exc)
        raise SystemExit(2) from exc

    bot = VerificationBot(config)
    try:
        bot.run(config.token, log_handler=None)
    except discord.LoginFailure as exc:
        LOGGER.critical("Discord token geçersiz.")
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
