import json
import discord
from discord.utils import MISSING
from discord.ext.commands import Cog, Bot
from discord.ext import tasks
from typing import List, Dict, Optional
from utils import utils
from datetime import datetime, timezone, timedelta
import re
import asyncio


MIN_TIME = datetime(1970, 1, 1, tzinfo=timezone.utc)
def get_time_ident(datetime : datetime) -> int:
    offset = datetime - MIN_TIME
    return int(offset.total_seconds() / 60)

def get_input_time(time_str:str) -> Optional[datetime]:
    if (re.fullmatch(r"^(\d+d\s?)?(\d+h\s?)?(\d+m)?$", time_str)):
    
        def get_duration_component(suffix:str, in_str:str) -> int:
            match : re.Match[str] = re.search(f"\d+{suffix}", in_str)
            if (match):
                return int(match.group().removesuffix(suffix))
            return 0
    
        days = get_duration_component("d", time_str)
        hours = get_duration_component("h", time_str)
        minutes = get_duration_component("m", time_str)
        return utils.utcnow() + timedelta(days=days, hours=hours, minutes=minutes)
    
    return None


# -----------------------------

class RemindMeData:

    class MessageData:
        def __init__(self, message:discord.Message):
            self.message_id = message.id
            self.channel_id = message.channel.id
            self.url = message.jump_url
        
        async def get_message(self, client:discord.Client) -> Optional[discord.Message]:
            channel = await client.fetch_channel(self.channel_id)
            return await channel.fetch_message(self.message_id)



    def __init__(self, user_id:int, text: Optional[str] = None, message: Optional[discord.Message] = None):
        self.ident : int = 0
        self.user_id = user_id
        self.text : Optional[str] = text
        self.message : Optional[RemindMeData.MessageData] = RemindMeData.MessageData(message) if message is not None else None
    
    def set_remind_time(self, time:datetime):
        self.ident = get_time_ident(time)

    async def get_embeds(self, client:discord.Client) -> Optional[List[discord.Embed]]:
        if self.text != None:
            embed : discord.Embed = discord.Embed()
            embed.add_field(name=self.text, value="")
            return [ embed ]
        elif self.message != None:
            message:discord.Message = await self.message.get_message(client)
            return utils.get_embeds_for_message(message)
        
        return None
    
    def get_original_message_view(self) -> Optional[discord.ui.View]:
        if self.message != None:
            return utils.get_view_for_url("Original Message", self.message.url)
        
        return None
    
# -----------------------------


class RemindMeContext:
    def __init__(self, message:discord.InteractionMessage):
        self.message = message


# -----------------------------


_all_reminders : List[RemindMeData] = []

# -----------------------------


class RemindMeView(discord.ui.View):
    
    options : List[discord.SelectOption] = [
        discord.SelectOption(label="5 min", value=f"{5}"),
        discord.SelectOption(label="30 min", value=f"{30}"),
        discord.SelectOption(label="1 hour", value=f"{60}"),
        discord.SelectOption(label="3 hours", value=f"{3*60}"),
        discord.SelectOption(label="6 hours", value=f"{6*60}"),
        discord.SelectOption(label="24 hours", value=f"{24*60}"),
        discord.SelectOption(label="Custom", value="custom")
    ]

    def __init__(self, data:RemindMeData, context:RemindMeContext):
        super().__init__(timeout=None)
        self.data = data
        self.context = context
        if (data.message != None):
            button = discord.ui.Button(label="Original Message", style=discord.ButtonStyle.url, url=data.message.url)
            self.add_item(button)

    
    @discord.ui.select(options=options, row=1, placeholder="Remind me in...")
    async def select_time(self, interaction:discord.Interaction, select:discord.ui.Select):
        if (select.values[0] == "custom"):
            modal = RemindMeModal()
            modal.set_data(self.data, self.context)
            await interaction.response.send_modal(modal)
        else:
            remind_date = utils.utcnow() + timedelta(minutes=int(select.values[0]))
            self.data.set_remind_time(remind_date)
            _all_reminders.append(self.data)
            await self.context.message.edit(content=f"Gotcha, I'll remind you about this on <t:{utils.get_timestamp(remind_date)}:f>", embeds=await self.data.get_embeds(interaction.client), view=self.data.get_original_message_view())

class RemindMeLaterView(discord.ui.View):

    def __init__(self, data : RemindMeData):
        super().__init__(timeout=180)
        self.data = data
        self.message = None
        if data.message != None:
            self.add_item(utils.get_url_button("Original Message", data.message.url))

    def set_message(self, message:discord.Message):
        self.message = message

    @discord.ui.button(label="Remind Me Later", row=1, style=discord.ButtonStyle.primary, emoji="😴")
    async def remind_me_later(self, interaction:discord.Interaction, button:discord.ui.Button):
        await self.reset_message_view()
        await interaction.response.defer(ephemeral=True, thinking=True)
        context = RemindMeContext(await interaction.original_response())
        view = RemindMeView(self.data, context)
        await interaction.edit_original_response(content=f"When would you like me to remind you about this again?", embeds=await self.data.get_embeds(interaction.client), view=view)

    async def on_timeout(self):
        await self.reset_message_view()

    async def reset_message_view(self):
        await self.message.edit(view=utils.get_view_for_url("Original Message", self.data.message.url))


# -----------------------------


class RemindMeModal(discord.ui.Modal, title="Remind Me"):
    _timeInput = discord.ui.TextInput(label="Time from now (Enter in the format #d #h #m)", placeholder="1d 1h 1m")

    def set_data(self, data:RemindMeData, context:RemindMeContext):
        self.data = data
        self.context = context

    async def on_submit(self, interaction:discord.Interaction):
        input_str = self._timeInput.value
        future_time = get_input_time(input_str)
        await interaction.response.defer()
        if future_time is not None:
            self.data.set_remind_time(future_time)
            _all_reminders.append(self.data)
            await self.context.message.edit(content=f"Gotcha, I'll remind you about this on <t:{utils.get_timestamp(future_time)}:f>", embeds=await self.data.get_embeds(interaction.client), view=self.data.get_original_message_view())
        else:
            view = RemindMeView(self.data, self.context)
            await self.context.message.edit(content=f"**\"{input_str}\"** doesn't follow the format `#d #h #m`. Select a valid time from the list or **Custom** to retry.", view=view, embeds=await self.data.get_embeds(interaction.client))


# -----------------------------


class RemindMeCog(Cog):
    def __init__(self, bot:Bot):
        self.bot = bot
        self.ctx_menu = discord.app_commands.ContextMenu(
            name="Remind Me",
            callback=self.remind_me_message
        )
        self.bot.tree.add_command(self.ctx_menu)
        self.minute_check.start()
    
    def cog_unload(self):
        print("Remind me cog unloaded!")
        if self.minute_check.is_running():
            self.minute_check.cancel()
        self.bot.tree.remove_command(self.ctx_menu)

    @tasks.loop(minutes=1)
    async def minute_check(self):
        global _all_reminders
        
        curr_ident = get_time_ident(utils.utcnow())
        curr_reminders : List[RemindMeData] = [ r for r in _all_reminders if r.ident == curr_ident ]

        for reminder in curr_reminders:
            try:
                user : discord.User = self.bot.get_user(reminder.user_id)
                view = RemindMeLaterView(reminder)
                message:discord.Message = await user.send("You asked me to remind you about this!", embeds=await reminder.get_embeds(self.bot), view=view)
                view.set_message(message)
            except Exception as e:
                print("Error when getting reminder for message!")
                print(e)


        if (len(curr_reminders) > 0):
            _all_reminders = [ r for r in _all_reminders if r.ident > curr_ident ] # remove all entries that have passed
        

    @minute_check.before_loop
    async def before_minute_check(self):
        while (utils.utcnow().second != 0):
            await asyncio.sleep(1)

    async def remind_me_message(self, interaction: discord.Interaction, message: discord.Message):
        await interaction.response.defer(ephemeral=True)
        context = RemindMeContext(await interaction.original_response())
        data = RemindMeData(interaction.user.id, message=message)
        view = RemindMeView(data, context)
        await context.message.edit(content="When would you like me to remind you about this message?", embeds= await data.get_embeds(self.bot), view=view)
        

    @discord.app_commands.command(description="Creates a reminder for a given message")
    async def remindme(self, interaction: discord.Interaction, message: str, time: str = None):
        await interaction.response.defer(ephemeral=True)
        data = RemindMeData(interaction.user.id, text=message)
        if time is not None:
            future_time = get_input_time(time)
            if future_time is not None:
                data.set_remind_time(future_time)
                _all_reminders.append(data)
                await utils.respond(interaction, f"Gotcha, I'll remind you about this on <t:{utils.get_timestamp(future_time)}:f>", embeds=await data.get_embeds(self.bot))
            else:
                await utils.respond(interaction, "There was a problem with that inputted time! Be sure to follow the format of `#d #h #m`", ephemeral=True)
        else:
            context = RemindMeContext(await interaction.original_response())
            view = RemindMeView(data, context)
            await context.message.edit(content=f"When would you like me to remind you about this?", embeds= await data.get_embeds(self.bot), view=view)


# -----------------------------

    
async def setup(bot : Bot):
    await bot.add_cog(RemindMeCog(bot))