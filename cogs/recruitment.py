# -*- coding: utf-8 -*-
"""
Maître — Система набора в команду (Recruitment).
"""

import logging
import re
from typing import Optional

import nextcord
from nextcord.ext import commands

log = logging.getLogger("maitre.recruitment")

APPLICATION_CHANNEL_ID = 1556056411358892243  # Канал, куда падают заявки
TESTER_ROLE_ID = 1569794957928177674          # Роль, которая выдается при принятии
STAFF_ROLE_ID = 1556054469559713822           # Роль модератора/рекрутера (кто может нажимать кнопки)

class ApplicationModal(nextcord.ui.Modal):
    def __init__(self):
        super().__init__(title="Заявка в команду Lounge", timeout=300)

        self.experience = nextcord.ui.TextInput(
            label="Опыт в тестировании",
            style=nextcord.TextInputStyle.paragraph,
            placeholder="Искал ли баги? Умеешь писать отчеты?",
            required=True,
            max_length=1000
        )
        self.time = nextcord.ui.TextInput(
            label="Свободное время",
            style=nextcord.TextInputStyle.short,
            placeholder="По МСК, сколько часов в неделю?",
            required=True,
            max_length=100
        )
        self.motivation = nextcord.ui.TextInput(
            label="Почему именно ты?",
            style=nextcord.TextInputStyle.paragraph,
            placeholder="Твоя мотивация",
            required=True,
            max_length=1000
        )

        self.add_item(self.experience)
        self.add_item(self.time)
        self.add_item(self.motivation)

    async def callback(self, interaction: nextcord.Interaction):
        await interaction.response.defer(ephemeral=True)

        channel = self.bot.get_channel(APPLICATION_CHANNEL_ID)
        if not channel:
            return await interaction.followup.send(
                "❌ Ошибка: канал для заявок не найден. Сообщите администрации.", ephemeral=True
            )

        embed = nextcord.Embed(
            title="📝 Новая заявка в команду",
            color=0xC5A028, # Золотой
            timestamp=nextcord.utils.utcnow()
        )
        # ВАЖНО: Форматируем поле так, чтобы из него можно было вытащить ID регуляркой
        embed.add_field(
            name="Кандидат",
            value=f"{interaction.user.mention} (ID: {interaction.user.id})",
            inline=False
        )
        embed.add_field(name="Опыт в тестировании", value=self.experience.value, inline=False)
        embed.add_field(name="Свободное время", value=self.time.value, inline=False)
        embed.add_field(name="Мотивация", value=self.motivation.value, inline=False)
        embed.set_footer(text="Lounge HQ • Recruitment")

        await channel.send(embed=embed, view=ModerationView())
        await interaction.followup.send(
            "✅ Ваша заявка отправлена! Мэтр рассмотрит её в ближайшее время.", ephemeral=True
        )

class ModerationView(nextcord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    def _extract_user_id(self, embed: nextcord.Embed) -> Optional[int]:
        """Достает ID кандидата из текста эмбеда (поле Кандидат)."""
        for field in embed.fields:
            if field.name == "Кандидат":
                match = re.search(r"\(ID:\s*(\d+)\)", field.value)
                if match:
                    return int(match.group(1))
        return None

    def _has_permission(self, member: nextcord.Member) -> bool:
        """Проверяет, может ли юзер модерировать заявки."""
        if member.guild_permissions.administrator:
            return True
        if any(role.id == STAFF_ROLE_ID for role in member.roles):
            return True
        return False

    async def _process_moderation(self, interaction: nextcord.Interaction, accepted: bool):
        if not self._has_permission(interaction.user):
            return await interaction.response.send_message(
                "❌ У вас нет прав для рассмотрения заявок.", ephemeral=True
            )

        embed = interaction.message.embeds[0]
        applicant_id = self._extract_user_id(embed)
        
        if not applicant_id:
            return await interaction.response.send_message(
                "❌ Не удалось определить ID кандидата из заявки.", ephemeral=True
            )

        guild = interaction.guild
        applicant = guild.get_member(applicant_id)
        if not applicant:
            try:
                applicant = await guild.fetch_member(applicant_id)
            except nextcord.NotFound:
                return await interaction.response.send_message(
                    "❌ Кандидат больше не на сервере.", ephemeral=True
                )

        # Отвечаем модератору, чтобы дискорд не ругался на таймаут
        await interaction.response.defer(ephemeral=True)

        status_field = "Статус: ❌ Отклонён"
        new_color = 0x992D22 # Красный
        dm_text = "🎩 К сожалению, ваша заявка в команду Lounge была отклонена. Возможно, в другой раз."

        if accepted:
            status_field = "Статус: ✅ Принят"
            new_color = 0x2ECC71 # Зеленый
            dm_text = "🎩 Ваша заявка в команду Lounge одобрена! Добро пожаловать."
            
            # Выдаем роль
            role = guild.get_role(TESTER_ROLE_ID)
            if role:
                try:
                    await applicant.add_roles(role, reason="Одобрение заявки в команду")
                except nextcord.Forbidden:
                    await interaction.followup.send("⚠️ Не удалось выдать роль (проверь иерархию ролей).", ephemeral=True)

        # Пытаемся отправить ЛС
        try:
            await applicant.send(dm_text)
        except nextcord.Forbidden:
            pass # Если у кандидата закрыты ЛС, просто игнорируем

        # Обновляем эмбед
        embed.add_field(name="Решение", value=status_field, inline=False)
        embed.color = new_color
        
        # Отключаем кнопки и обновляем сообщение
        await interaction.message.edit(embed=embed, view=None)
        
        result_text = "Заявка принята." if accepted else "Заявка отклонена."
        await interaction.followup.send(f"✅ {result_text}", ephemeral=True)

    @nextcord.ui.button(label="Принять", style=nextcord.ButtonStyle.success, emoji="✅", custom_id="app_accept")
    async def accept(self, button: nextcord.ui.Button, interaction: nextcord.Interaction):
        await self._process_moderation(interaction, accepted=True)

    @nextcord.ui.button(label="Отклонить", style=nextcord.ButtonStyle.danger, emoji="❌", custom_id="app_reject")
    async def reject(self, button: nextcord.ui.Button, interaction: nextcord.Interaction):
        await self._process_moderation(interaction, accepted=False)

class RecruitPanelView(nextcord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @nextcord.ui.button(label="Подать заявку", style=nextcord.ButtonStyle.primary, emoji="📝", custom_id="apply_team")
    async def apply(self, button: nextcord.ui.Button, interaction: nextcord.Interaction):
        modal = ApplicationModal()
        modal.bot = interaction.client # Прокидываем бота в модалку, чтобы найти канал
        await interaction.response.send_modal(modal)

class Recruitment(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Регистрируем постоянные вьюхи
        self.bot.add_view(RecruitPanelView())
        self.bot.add_view(ModerationView())

    @nextcord.slash_command(
        name="recruit-panel", 
        description="Отправить панель набора в команду",
        default_member_permissions=nextcord.Permissions(administrator=True)
    )
    async def recruit_panel(self, interaction: nextcord.Interaction):
        embed = nextcord.Embed(
            title="🎩 Набор в команду Lounge",
            description=(
                "Мы ищем **тестировщиков** для проекта Lounge. "
                "Если ты любишь настолки, внимателен к деталям и хочешь помочь проекту — заполни заявку.\n\n"
                "*Мэтр лично рассмотрит каждую.*"
            ),
            color=0xC5A028
        )
        embed.set_footer(text="Lounge HQ • Recruitment")
        
        await interaction.channel.send(embed=embed, view=RecruitPanelView())
        await interaction.response.send_message("✅ Панель набора опубликована.", ephemeral=True)

def setup(bot: commands.Bot):
    bot.add_cog(Recruitment(bot))