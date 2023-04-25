import json
import discord
from discord.utils import MISSING
from discord.ext.commands import Cog, Bot
from discord.ext import tasks
from typing import List, Dict, Optional
from utils import utils, db
from datetime import datetime, timezone, timedelta
import re
import asyncio
import sqlite3


MIN_TIME = datetime(1970, 1, 1, tzinfo=timezone.utc)
def get_time_ident(datetime : datetime) -> int:
    offset = datetime - MIN_TIME
    return int(offset.total_seconds() / 60)

connection : sqlite3.Connection = sqlite3.connect("data/remindme/reminders.db")

db.execute_command(connection, """
    CREATE TABLE IF NOT EXISTS "reminders" (
        ident INTEGER,
        user_id INTEGER,
        text TEXT,
        message_id INTEGER,
        channel_id INTEGER,
        url TEXT,
        timestamp INTEGER
    )
""")

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
        
        # Check for time > 0
        if days + hours + minutes > 0:
            return utils.utcnow() + timedelta(days=days, hours=hours, minutes=minutes)
    
    return None


# -----------------------------

class RemindMeData:

    class MessageData:
        def __init__(self):
            self.message_id:int = 0
            self.channel_id:int = 0
            self.url:str = ""
        
        def from_message(self, message:discord.Message):
            self.message_id = message.id
            self.channel_id = message.channel.id
            self.url = message.jump_url
            return self
        
        def from_data(self, message_id:int, channel_id:int, url:str):
            self.message_id = message_id
            self.channel_id = channel_id
            self.url = url
            return self

        async def get_message(self, client:discord.Client) -> Optional[discord.Message]:
            channel = await client.fetch_channel(self.channel_id)
            return await channel.fetch_message(self.message_id)



    def __init__(self, user_id:int, text: Optional[str] = None, message: Optional[discord.Message] = None, message_data: Optional[MessageData] = None):
        self.ident : int = 0
        self.timestamp : int = 0
        self.user_id = user_id
        self.text : Optional[str] = text
        self.message = None
        if message_data is not None:
            self.message = message_data
        elif message is not None:
            self.message = RemindMeData.MessageData().from_message(message)

    def set_ident_from_remind_time(self, time:datetime):
        self.ident = get_time_ident(time)
        self.timestamp = utils.get_timestamp(time)

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

def add_reminder_to_db(reminder:RemindMeData):
    message_id = None
    channel_id = None
    url = None
    if reminder.message is not None:
        message_id = reminder.message.message_id
        channel_id = reminder.message.channel_id
        url = reminder.message.url
    db.execute_command(connection, """
        INSERT INTO reminders
            (ident, user_id, text, message_id, channel_id, url, timestamp)
            VALUES (?,?,?,?,?,?,?)
    """, (reminder.ident, reminder.user_id, reminder.text, message_id, channel_id, url, reminder.timestamp))

def _db_reminder_to_data(entry) -> RemindMeData:
    ident = entry[0]
    user_id = entry[1]
    text = entry[2]
    message_id = entry[3]
    channel_id = entry[4]
    url = entry[5]
    timestamp = entry[6]

    message = None
    if message_id is not None:
        message = RemindMeData.MessageData().from_data(message_id, channel_id, url)
    data = RemindMeData(user_id, text, message_data=message)
    data.ident = ident
    data.timestamp = timestamp
    return data


def _db_reminders_to_data(db_data) -> List[RemindMeData]:
    data_list : List[RemindMeData] = []
    
    for entry in db_data:
        data_list.append(_db_reminder_to_data(entry))

    return data_list
        

def _clear_old_reminders(ident:int):
    db.execute_command(connection, """
        DELETE FROM reminders
        WHERE ident <= ?
    """, (ident,))

def get_reminders_for_ident(ident:int) -> List[RemindMeData]:
    data = db.get_data(connection, """
        SELECT
            *
        FROM 
            reminders
        WHERE
            ident = ?
    """, (ident,))
    data_list = _db_reminders_to_data(data)
    _clear_old_reminders(ident)
    return data_list
    
def get_reminder_with_id(id:int) -> RemindMeData:
    entry = db.get_single_row(connection, """
        SELECT
            *
        FROM
            reminders
        WHERE
            rowid = ?
        LIMIT 1
    """,(id,))
    return _db_reminder_to_data(entry)

# Returns only the db row identifiers for a given user
def get_reminder_ids_for_user(user_id:int) -> List[int]:
    data = db.get_data(connection, """
        SELECT
            rowid
        FROM 
            reminders
        WHERE
            user_id = ?
        ORDER BY
            ident
    """, (user_id,))

    return [ x[0] for x in data ]

class RemindMeContext:
    def __init__(self, message:discord.InteractionMessage):
        self.message = message

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
            self.data.set_ident_from_remind_time(remind_date)
            add_reminder_to_db(self.data)
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
        await self.message.edit(view=self.data.get_original_message_view())


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
            self.data.set_ident_from_remind_time(future_time)
            add_reminder_to_db(self.data)
            await self.context.message.edit(content=f"Gotcha, I'll remind you about this on <t:{utils.get_timestamp(future_time)}:f>", embeds=await self.data.get_embeds(interaction.client), view=self.data.get_original_message_view())
        else:
            view = RemindMeView(self.data, self.context)
            await self.context.message.edit(content=f"**\"{input_str}\"** is either invalid or doesn't follow the format `#d #h #m`. Select a valid time from the list or **Custom** to retry.", view=view, embeds=await self.data.get_embeds(interaction.client))


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
        
        curr_ident = get_time_ident(utils.utcnow())
        curr_reminders : List[RemindMeData] = get_reminders_for_ident(curr_ident)

        for reminder in curr_reminders:
            try:
                user : discord.User = self.bot.get_user(reminder.user_id)
                view = RemindMeLaterView(reminder)
                message:discord.Message = await user.send("You asked me to remind you about this!", embeds=await reminder.get_embeds(self.bot), view=view)
                view.set_message(message)
            except Exception as e:
                print("Error when getting reminder for message!")
                print(e)
        

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
                data.set_ident_from_remind_time(future_time)
                add_reminder_to_db(data)
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