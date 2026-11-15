from __future__ import annotations

import logging
import os
import re
from typing import Dict, List, Optional

import nextcord
from nextcord.ext import commands

log = logging.getLogger("maitre.tickets")

def _env_int(name: str) -> Optional[int]:
    raw = os.getenv(name, "").strip().strip("'\"")
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        log.warning("TICKET: %s=%r — не число, значение проигнорировано", name, raw)
        return None

TICKET_CONFIG: Dict[str, Optional[int]] = {
    "CATEGORY_ID": 1569060754668261567,
    "SUPPORT_ROLE_ID": 1556054908602421329,
    "LOG_CHANNEL_ID": 1556056440580345898,
}

OWNER_MARKER = "maitre-owner:"
_OWNER_RE = re.compile(r"maitre-owner:(\d+)")
_LEGACY_NAME_RE = re.compile(r"^ticket-(\d{15,25})$")
_INVALID_CHARS_RE = re.compile(r"[^\w\-]+", re.UNICODE)
_MULTI_DASH_RE = re.compile(r"-{2,}")

PANEL_TITLE = "🎩 Приемная Maître"
PANEL_DESCRIPTION = (
    "Добро пожаловать в приемную, леди и джентльмены.\n\n"
    "**Maître** — неизменно вежливый и неизменно полезный — готов выслушать вас "
    "и разрешить любой вопрос: техническая неурядица, спор о правилах, "
    "просьба о помощи или просто желание поговорить по существу.\n\n"
    "__*Прикоснитесь к конверту ниже, и для вас будет отведена отдельная комната.*__"
)

WELCOME_DESCRIPTION = (
    "Опишите вашу проблему, и Мэтр скоро подойдёт.\n\n"
    "__Один вопрос — один тикет. Чем точнее формулировка, тем быстрее последует ответ.__"
)

def sanitize_channel_name(raw: str, max_len: int = 90) -> str:
    """Приводит произвольную строку к виду, допустимому в имени канала Discord."""
    name = (raw or "").strip().lower()
    name = _INVALID_CHARS_RE.sub("-", name)
    name = _MULTI_DASH_RE.sub("-", name).strip("-_")
    return name[:max_len] or "user"


class TicketSystem(commands.Cog, name="Тикеты"):
    """Обращения в поддержку Maître: панель, создание и закрытие тикетов."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.config = TICKET_CONFIG
        self.bot.add_view(TicketPanelView(self))
        self.bot.add_view(CloseTicketView(self))

    def _missing_config(self) -> List[str]:
        return [key for key, value in self.config.items() if not value]

    @staticmethod
    def _config_error_embed(missing: List[str]) -> nextcord.Embed:
        embed = nextcord.Embed(
            title="⚙️ Система тикетов не настроена",
            description="Заполните переменные окружения: " + ", ".join(f"`{k}`" for k in missing),
            color=nextcord.Color.orange(),
        )
        return embed

    def _is_support(self, member: nextcord.Member) -> bool:
        """Сотрудник поддержки: админ, право manage_channels или роль SUPPORT_ROLE_ID."""
        perms = member.guild_permissions
        if perms.administrator or perms.manage_channels:
            return True
        role_id = self.config["SUPPORT_ROLE_ID"]
        return role_id is not None and any(r.id == role_id for r in member.roles)

    @staticmethod
    def _ticket_owner_id(channel: nextcord.TextChannel) -> Optional[int]:
        match = _OWNER_RE.search(channel.topic or "")
        if match:
            return int(match.group(1))
        legacy = _LEGACY_NAME_RE.match(channel.name or "")
        return int(legacy.group(1)) if legacy else None

    def _looks_like_ticket(self, channel: nextcord.TextChannel) -> bool:
        if self.config["CATEGORY_ID"] and channel.category_id == self.config["CATEGORY_ID"]:
            return True
        return (channel.name or "").startswith("ticket-")

    async def _find_open_ticket(
        self,
        guild: nextcord.Guild,
        member: nextcord.Member,
        category: Optional[nextcord.CategoryChannel] = None,
    ) -> Optional[nextcord.TextChannel]:
        if category is None:
            category = guild.get_channel(self.config["CATEGORY_ID"])

        pool = list(category.text_channels) if isinstance(category, nextcord.CategoryChannel) else list(guild.text_channels)
        for channel in pool:
            if self._ticket_owner_id(channel) == member.id:
                return channel
            
        candidates = {f"ticket-{member.id}", f"ticket-{sanitize_channel_name(member.display_name)}"}
        for channel in pool:
            if channel.name in candidates:
                return channel
        return None

    @staticmethod
    def _unique_name(guild: nextcord.Guild, base: str) -> str:
        taken = {c.name for c in guild.text_channels}
        if base not in taken:
            return base
        for index in range(2, 100):
            candidate = f"{base[: 95]}-{index}"
            if candidate not in taken:
                return candidate
        return f"{base[: 80]}-{os.urandom(3).hex()}"

    @nextcord.slash_command(
        name="ticket-panel",
        description="Отправить панель обращений в поддержку (только администратор).",
        default_member_permissions=nextcord.Permissions(administrator=True),
    )
    async def ticket_panel(self, interaction: nextcord.Interaction) -> None:
        member = interaction.user
        if not isinstance(member, nextcord.Member) or not member.guild_permissions.administrator:
            await interaction.response.send_message(
                "Эта команда доступна только администраторам.", ephemeral=True
            )
            return

        if interaction.channel is None or not isinstance(interaction.channel, nextcord.TextChannel):
            await interaction.response.send_message(
                "Панель можно отправить только в текстовый канал сервера.", ephemeral=True
            )
            return

        missing = self._missing_config()
        if missing:
            await interaction.response.send_message(embed=self._config_error_embed(missing), ephemeral=True)
            return

        embed = nextcord.Embed(
            title=PANEL_TITLE,
            description=PANEL_DESCRIPTION,
            color=nextcord.Color.from_rgb(0x9B, 0x1B, 0x1B),
        )
        embed.set_footer(text="Maître • конфиденциально и по существу")

        try:
            await interaction.channel.send(embed=embed, view=TicketPanelView(self))
        except nextcord.Forbidden:
            await interaction.response.send_message(
                "У бота нет прав отправлять сообщения в этот канал.", ephemeral=True
            )
            return

        await interaction.response.send_message("Панель обращений опубликована.", ephemeral=True)

    async def handle_open(self, interaction: nextcord.Interaction) -> None:
        guild, member = interaction.guild, interaction.user
        if guild is None or not isinstance(member, nextcord.Member):
            await interaction.response.send_message(
                "Обращения доступны только на сервере.", ephemeral=True
            )
            return

        missing = self._missing_config()
        if missing:
            await interaction.response.send_message(embed=self._config_error_embed(missing), ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, with_message=True)

        category = guild.get_channel(self.config["CATEGORY_ID"])
        if not isinstance(category, nextcord.CategoryChannel):
            await interaction.followup.send(
                "Категория для тикетов не найдена. Сообщите администратору.", ephemeral=True
            )
            return

        bot_member = guild.me or guild.get_member(self.bot.user.id)
        if bot_member is None or not bot_member.guild_permissions.manage_channels:
            await interaction.followup.send(
                "У бота нет права «Управлять каналами» — тикет создать нельзя.", ephemeral=True
            )
            return

        try:
            existing = await self._find_open_ticket(guild, member, category)
        except nextcord.HTTPException:
            log.exception("Не удалось проверить наличие открытого тикета")
            existing = None

        if existing is not None:
            await interaction.followup.send(
                f"У вас уже есть открытое обращение: {existing.mention}", ephemeral=True
            )
            return

        base_name = f"ticket-{sanitize_channel_name(member.display_name)}"
        channel_name = self._unique_name(guild, base_name)

        support_role: Optional[nextcord.Role] = (
            guild.get_role(self.config["SUPPORT_ROLE_ID"]) if self.config["SUPPORT_ROLE_ID"] else None
        )

        overwrites: Dict[nextcord.abc.GuildChannel, nextcord.PermissionOverwrite] = {
            guild.default_role: nextcord.PermissionOverwrite(view_channel=False),
            member: nextcord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
                embed_links=True,
            ),
            (bot_member or guild.me): nextcord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                manage_channels=True,
                manage_messages=True,
                read_message_history=True,
                attach_files=True,
                embed_links=True,
            ),
        }
        if support_role is not None:
            overwrites[support_role] = nextcord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
                embed_links=True,
            )

        try:
            channel = await guild.create_text_channel(
                name=channel_name,
                category=category,
                overwrites=overwrites,
                topic=f"{OWNER_MARKER}{member.id} | Тикет Maître",
                reason=f"Тикет открыт: {member} ({member.id})",
            )
        except nextcord.Forbidden:
            await interaction.followup.send(
                "Не удалось создать канал: у бота нет прав в этой категории.", ephemeral=True
            )
            return
        except nextcord.HTTPException as exc:
            log.exception("HTTPException при создании тикета")
            await interaction.followup.send(
                f"Discord отклонил создание канала (`{exc.status}`). Попробуйте позже.", ephemeral=True
            )
            return

        welcome = nextcord.Embed(
            title="🎩 Добро пожаловать в приемную",
            description=f"{member.mention}, {WELCOME_DESCRIPTION}",
            color=nextcord.Color.from_rgb(0x2E, 0x7D, 0x32),
        )
        welcome.add_field(name="Автор обращения", value=f"{member} (`{member.id}`)", inline=True)
        welcome.add_field(name="Статус", value="🟢 Ожидает ответа", inline=True)
        welcome.set_footer(text="Закрыть обращение можно кнопкой ниже")

        try:
            await channel.send(content=member.mention, embed=welcome, view=CloseTicketView(self))
        except (nextcord.Forbidden, nextcord.HTTPException):
            log.exception("Не удалось отправить приветствие в тикет %s", channel.id)
            try:
                await channel.delete(reason="Не удалось инициализировать тикет")
            except (nextcord.Forbidden, nextcord.HTTPException):
                pass
            await interaction.followup.send(
                "Канал создан, но бот не смог отправить в него сообщение. Канал удалён.", ephemeral=True
            )
            return

        await interaction.followup.send(f"Ваше обращение открыто: {channel.mention}", ephemeral=True)

    async def handle_close_request(self, interaction: nextcord.Interaction) -> None:
        channel, member = interaction.channel, interaction.user
        if not isinstance(channel, nextcord.TextChannel) or not isinstance(member, nextcord.Member):
            await interaction.response.send_message(
                "Кнопка работает только внутри канала тикета.", ephemeral=True
            )
            return

        if not self._looks_like_ticket(channel):
            await interaction.response.send_message(
                "Это не канал обращения.", ephemeral=True
            )
            return

        owner_id = self._ticket_owner_id(channel)
        is_owner = owner_id is not None and member.id == owner_id
        if not (is_owner or self._is_support(member)):
            await interaction.response.send_message(
                "Закрыть обращение может только его автор или сотрудник поддержки.", ephemeral=True
            )
            return

        embed = nextcord.Embed(
            title="🔒 Закрыть обращение?",
            description="Канал будет удалён без возможности восстановления.\n"
                        "История сохранится только в логах сервера.",
            color=nextcord.Color.orange(),
        )
        await interaction.response.send_message(
            embed=embed,
            view=CloseConfirmView(self, channel=channel, owner_id=owner_id),
            ephemeral=True,
        )

    async def close_ticket(
        self,
        interaction: nextcord.Interaction,
        channel: nextcord.TextChannel,
        closer: nextcord.Member,
    ) -> None:
        try:
            await interaction.response.edit_message(
                embed=nextcord.Embed(
                    title="🔒 Тикет закрывается",
                    description=f"Канал `{channel.name}` будет удалён.",
                    color=nextcord.Color.dark_red(),
                ),
                view=None,
            )
        except (nextcord.HTTPException, nextcord.NotFound):
            log.debug("Не удалось обновить сообщение подтверждения", exc_info=True)

        await self._send_close_log(channel, closer)

        try:
            await channel.delete(reason=f"Тикет закрыт: {closer} ({closer.id})")
        except nextcord.Forbidden:
            await interaction.followup.send(
                "Не удалось удалить канал: у бота нет права «Управлять каналами».", ephemeral=True
            )
        except nextcord.NotFound:
            log.info("Канал тикета %s уже удалён", channel.id)
        except nextcord.HTTPException:
            log.exception("Ошибка удаления канала тикета %s", channel.id)
            try:
                await interaction.followup.send(
                    "Discord не дал удалить канал. Попробуйте ещё раз.", ephemeral=True
                )
            except nextcord.HTTPException:
                pass

    async def _send_close_log(self, channel: nextcord.TextChannel, closer: nextcord.Member) -> None:
        guild = channel.guild
        log_channel = guild.get_channel(self.config["LOG_CHANNEL_ID"]) if self.config["LOG_CHANNEL_ID"] else None
        if not isinstance(log_channel, nextcord.TextChannel):
            log.warning("Канал логов тикетов не найден — запись только в консоль")
            return

        owner_id = self._ticket_owner_id(channel)
        owner: Optional[nextcord.Member] = guild.get_member(owner_id) if owner_id else None
        if owner is None and owner_id:
            try:
                owner = await guild.fetch_member(owner_id)
            except (nextcord.NotFound, nextcord.HTTPException):
                owner = None

        embed = nextcord.Embed(
            title="📋 Тикет закрыт",
            color=nextcord.Color.dark_red(),
            timestamp=nextcord.utils.utcnow(),
        )
        embed.add_field(name="Канал", value=f"`{channel.name}` (`{channel.id}`)", inline=False)
        embed.add_field(
            name="Открыл",
            value=f"{owner.mention} (`{owner.id}`)" if owner else f"Неизвестно (`{owner_id}`)",
            inline=True,
        )
        embed.add_field(name="Закрыл", value=f"{closer.mention} (`{closer.id}`)", inline=True)
        embed.set_footer(text="Maître • журнал приемной")

        try:
            await log_channel.send(embed=embed)
        except (nextcord.Forbidden, nextcord.HTTPException):
            log.exception("Не удалось отправить лог закрытия тикета в %s", log_channel.id)

class TicketPanelView(nextcord.ui.View):

    def __init__(self, cog: TicketSystem) -> None:
        super().__init__(timeout=None)
        self.cog = cog

    @nextcord.ui.button(
        label="Открыть обращение",
        emoji="📩",
        style=nextcord.ButtonStyle.success,
        custom_id="open_ticket",
    )
    async def open_ticket(self, button: nextcord.ui.Button, interaction: nextcord.Interaction) -> None:
        await self.cog.handle_open(interaction)


class CloseTicketView(nextcord.ui.View):

    def __init__(self, cog: TicketSystem) -> None:
        super().__init__(timeout=None)
        self.cog = cog

    @nextcord.ui.button(
        label="Закрыть тикет",
        emoji="🔒",
        style=nextcord.ButtonStyle.danger,
        custom_id="close_ticket",
    )
    async def close_ticket(self, button: nextcord.ui.Button, interaction: nextcord.Interaction) -> None:
        await self.cog.handle_close_request(interaction)


class CloseConfirmView(nextcord.ui.View):

    def __init__(self, cog: TicketSystem, *, channel: nextcord.TextChannel, owner_id: Optional[int]) -> None:
        super().__init__(timeout=120)
        self.cog = cog
        self.channel = channel
        self.owner_id = owner_id

    async def interaction_check(self, interaction: nextcord.Interaction) -> bool:
        member = interaction.user
        if not isinstance(member, nextcord.Member):
            return False
        if (self.owner_id is not None and member.id == self.owner_id) or self.cog._is_support(member):
            return True
        await interaction.response.send_message(
            "Подтвердить закрытие может только автор обращения или сотрудник поддержки.",
            ephemeral=True,
        )
        return False

    @nextcord.ui.button(
        label="Да, закрыть",
        emoji="✅",
        style=nextcord.ButtonStyle.danger,
    )
    async def confirm(self, button: nextcord.ui.Button, interaction: nextcord.Interaction) -> None:
        if not isinstance(interaction.user, nextcord.Member):
            return
        self.stop()
        await self.cog.close_ticket(interaction, self.channel, interaction.user)

    @nextcord.ui.button(
        label="Отмена",
        emoji="↩️",
        style=nextcord.ButtonStyle.secondary,
    )
    async def cancel(self, button: nextcord.ui.Button, interaction: nextcord.Interaction) -> None:
        self.stop()
        await interaction.response.edit_message(
            embed=nextcord.Embed(
                title="Отменено",
                description="Тикет остаётся открытым. Мэтр непременно вернётся к вам.",
                color=nextcord.Color.green(),
            ),
            view=None,
        )

def setup(bot: commands.Bot) -> None:
    bot.add_cog(TicketSystem(bot))