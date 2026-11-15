import nextcord
from nextcord.ext import commands
from nextcord import Interaction

class Verify(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @nextcord.slash_command(name="verify", description="Верифицироваться на сервере")
    async def verify_slash(self, interaction: Interaction):
        await self._verify_command(interaction)

    @commands.command(name="verify", description="Верифицирует пользователя на сервере")
    async def verify_prefix(self, ctx):
        await self._verify_command(ctx)

    async def _verify_command(self, context):
        guild = context.guild

        chat = guild.get_channel(1556055948789817395)
        verify_role = guild.get_role(1556054974843064412)
        allowed_channel_id = 1556068283415924838

        # Команда принимается только в указанном канале
        if context.channel.id != allowed_channel_id:
            if isinstance(context, Interaction):
                await context.response.send_message(
                    f"❌ Команду можно использовать только в <#{allowed_channel_id}>.",
                    ephemeral=True
                )
            else:
                await context.reply(
                    f"❌ Команду можно использовать только в <#{allowed_channel_id}>.",
                    delete_after=5
                )
            return

        if verify_role in context.author.roles:
            if isinstance(context, Interaction):
                await context.response.send_message(
                    "❌ Вы уже верифицированы.",
                    ephemeral=True
                )
            else:
                await context.reply("❌ Вы уже верифицированы.", delete_after=5)
            return

        try:
            if isinstance(context, Interaction):
                await context.response.defer(ephemeral=True)
                await context.delete_original_response()
            else:
                await context.message.delete()
        except:
            pass

        await context.author.add_roles(verify_role)

        emb = nextcord.Embed(
            description=(
                "🎩 **LOUNGE HQ** — *Good Games Only.*\n\n"
                "Приветствую, путник(-ца)．\n"
                "Ты переступил порог **дома Mr. Lounge**．\n\n"
                "Здесь не играют в поддавки — здесь играют **по-крупному**：\n"
                "🎭 Мафия • 🏚️ Бункер • 🎲 Казино\n\n"
                "Присаживайся．Но сперва — **ознакомься**：\n\n"
                "◞ <#1556055982860406784>\n"
                "*Джентльмены не читают правила дважды.* 🥃"
            ),
            color=0xC5A028,
        )
        ping_role_ids = []
        mentions = ' '.join([f'<@&{role_id}>' for role_id in ping_role_ids])
        await chat.send(
            content=f'{context.author.mention} {mentions}',
            embed=emb
        )

        if isinstance(context, Interaction):
            await context.followup.send("✅ Вы успешно верифицированы！", ephemeral=True)

def setup(bot):
    bot.add_cog(Verify(bot))