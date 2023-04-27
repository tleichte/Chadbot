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
import os

MIN_TIME = datetime(1970, 1, 1, tzinfo=timezone.utc)
def get_time_ident(datetime : datetime) -> int:
    offset = datetime - MIN_TIME
    return int(offset.total_seconds() / 60)

db_folder_path = "data/remindme"
db_path = "data/remindme/reminders.db"
if not os.path.exists(db_folder_path):
    os.makedirs(db_folder_path)

connection : sqlite3.Connection = sqlite3.connect(db_path)

db.execute_command(connection, """
    CREATE TABLE IF NOT EXISTS "reminders" (
        ident INTEGER,
        user_id INTEGER,
        note TEXT,
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

def get_input_time(days:int, hours:int, minutes:int):
    return utils.utcnow() + timedelta(days=days, hours=hours, minutes=minutes)

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



    def __init__(self, user_id:int, note: Optional[str] = None, message: Optional[discord.Message] = None, message_data: Optional[MessageData] = None):
        self.ident : int = 0
        self.timestamp : int = 0
        self.user_id = user_id
        self.note : Optional[str] = note
        self.message = None
        if message_data is not None:
            self.message = message_data
        elif message is not None:
            self.message = RemindMeData.MessageData().from_message(message)

    def set_ident_from_remind_time(self, time:datetime):
        self.ident = get_time_ident(time)
        self.timestamp = utils.get_timestamp(time)

    async def get_embeds(self, client:discord.Client) -> Optional[List[discord.Embed]]:
        if self.note != None:
            embed : discord.Embed = discord.Embed()
            embed.add_field(name=self.note, value="")
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
            (ident, user_id, note, message_id, channel_id, url, timestamp)
            VALUES (?,?,?,?,?,?,?)
    """, (reminder.ident, reminder.user_id, reminder.note, message_id, channel_id, url, reminder.timestamp))

def _db_reminder_to_data(entry) -> RemindMeData:
    ident = entry[0]
    user_id = entry[1]
    note = entry[2]
    message_id = entry[3]
    channel_id = entry[4]
    url = entry[5]
    timestamp = entry[6]

    message = None
    if message_id is not None:
        message = RemindMeData.MessageData().from_data(message_id, channel_id, url)
    data = RemindMeData(user_id, note, message_data=message)
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
    
def remove_reminder_with_id(id:int):
    db.execute_command(connection, """
        DELETE FROM reminders
        WHERE rowid = ?
    """, (id,))

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
        discord.SelectOption(label="5 minutes", value=f"{5}"),
        discord.SelectOption(label="30 minutes", value=f"{30}"),
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


class RemindMeModal(discord.ui.Modal, title="When should I remind you?"):

    _daysInput = discord.ui.TextInput(label="Days", placeholder="0", required=False, max_length=5)
    _hoursInput = discord.ui.TextInput(label="Hours", placeholder="0", required=False, max_length=5)
    _minutesInput = discord.ui.TextInput(label="Minutes", placeholder="0", required=False, max_length=5)
    # _timeInput = discord.ui.TextInput(label="Format as #d #h #m (i.e. 5m | 3h 15m | 1d 6h)", placeholder="0d 0h 0m")

    def set_data(self, data:RemindMeData, context:RemindMeContext):
        self.data = data
        self.context = context

    async def on_submit(self, interaction:discord.Interaction):

        def check_input(input:discord.ui.TextInput) -> int:
            if len(input.value.strip()) == 0:
                return 0
            if input.value.isdigit():
                return int(input.value)

            return None

        days = check_input(self._daysInput)
        hours = check_input(self._hoursInput)
        minutes = check_input(self._minutesInput)

        is_invalid : bool = False
        is_invalid = is_invalid or days is None
        is_invalid = is_invalid or hours is None
        is_invalid = is_invalid or minutes is None
        is_invalid = is_invalid or days + hours + minutes <= 0
        
        await interaction.response.defer()

        if is_invalid:
            out_str = f"{0 if days is None else days}d {self._hoursInput.value}h {self._minutesInput.value}m"
            view = RemindMeView(self.data, self.context)
            await self.context.message.edit(content=f"The entered time was not valid. Select a valid time from the list or **Custom** to retry.", view=view, embeds=await self.data.get_embeds(interaction.client))
        else:
            future_time = get_input_time(days, hours, minutes)
            self.data.set_ident_from_remind_time(future_time)
            add_reminder_to_db(self.data)
            await self.context.message.edit(content=f"Gotcha, I'll remind you about this on <t:{utils.get_timestamp(future_time)}:f>", embeds=await self.data.get_embeds(interaction.client), view=self.data.get_original_message_view())


# -----------------------------

class ActiveReminderView(discord.ui.View):
        def __init__(self, ids: List[int], message:discord.Message):
            super().__init__()
            self.ids = ids
            self.message = message
            self.index = 0

            self.url_button : discord.ui.Button = discord.ui.Button(label="Original Message", url="")
            self.included_url_button = False

            self.prev_button : discord.ui.Button = None
            self.delete_button : discord.ui.Button = None
            self.next_button : discord.ui.Button = None

            for child in self.children:
                if type(child) == discord.ui.Button:
                    if child.custom_id == "prev":
                        self.prev_button = child
                    elif child.custom_id == "delete":
                        self.delete_button = child
                    elif child.custom_id == "next":
                        self.next_button = child
            
            self.initial_buttons_added = False
            self.remove_item(self.prev_button)
            self.remove_item(self.delete_button)
            self.remove_item(self.next_button)

        @discord.ui.button(label="<", custom_id="prev", style=discord.ButtonStyle.blurple, row=1)
        async def prev_button_callback(self, interaction:discord.Interaction, button:discord.ui.Button):
            self.index -= 1
            await self.update(self.message, interaction.client)
            await interaction.response.defer()

        @discord.ui.button(label="Delete", custom_id="delete", style=discord.ButtonStyle.danger, row=1)
        async def delete_callback(self, interaction:discord.Interaction, button:discord.ui.Button):
            id = self.ids[self.index]
            self.ids.remove(id)
            self.index = min(len(self.ids) - 1, self.index)
            remove_reminder_with_id(id)

            if len(self.ids) > 0:
                await self.update(self.message, interaction.client)
            else:
                await self.message.edit(content="You have no reminders! Set one by using **/remind_me** or by right clicking a message and selecting **Apps -> Remind Me**", view=None, embed=None)
            await interaction.response.defer()

        @discord.ui.button(label=">", custom_id="next", style=discord.ButtonStyle.blurple, row=1)
        async def next_button_callback(self, interaction:discord.Interaction, button:discord.ui.Button):
            self.index += 1
            await self.update(self.message, interaction.client)
            await interaction.response.defer()

        async def on_timeout(self):
            await self.message.delete()

        async def update(self, message:discord.InteractionMessage, client:discord.Client):
            self.prev_button.disabled = self.index <= 0
            self.next_button.disabled = self.index >= len(self.ids)-1
            data = get_reminder_with_id(self.ids[self.index])
            if data.message != None:
                self.url_button.url = data.message.url
                if not self.included_url_button:
                    self.add_item(self.url_button)
            elif self.included_url_button:
                self.remove_item(self.url_button)
            
            self.included_url_button = data.message != None
            
            if not self.initial_buttons_added:
                self.initial_buttons_added = True
                self.add_item(self.prev_button)
                self.add_item(self.delete_button)
                self.add_item(self.next_button)

            await message.edit(content=f"**Reminder {self.index+1} / {len(self.ids)}**\nYou asked me to remind you about this on <t:{data.timestamp}:f>", embeds=await data.get_embeds(client), view=self)


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
        

    @discord.app_commands.command(description="Creates a reminder for a given note")
    async def remind_me(self, interaction: discord.Interaction, note: str, days: discord.app_commands.Range[int, 1, 1000] = None, hours: discord.app_commands.Range[int, 1, 1000] = None, minutes: discord.app_commands.Range[int, 1, 1000] = None):
        await interaction.response.defer(ephemeral=True)
        data = RemindMeData(interaction.user.id, note=note)
        if days is not None or hours is not None or minutes is not None:
            days = days or 0
            hours = hours or 0
            minutes = minutes or 0
            future_time = get_input_time(days, hours, minutes)
            # if future_time is not None:
            data.set_ident_from_remind_time(future_time)
            add_reminder_to_db(data)
            await utils.respond(interaction, f"Gotcha, I'll remind you about this on <t:{utils.get_timestamp(future_time)}:f>", embeds=await data.get_embeds(self.bot))
            # else:
            #     await utils.respond(interaction, "There was a problem with that inputted time! Be sure to follow the format of `#d #h #m`", ephemeral=True)
        else:
            context = RemindMeContext(await interaction.original_response())
            view = RemindMeView(data, context)
            await context.message.edit(content=f"When would you like me to remind you about this?", embeds= await data.get_embeds(self.bot), view=view)


    @discord.app_commands.command(description="Shows all your currently active reminders")
    async def my_reminders(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        ids : List[int] = get_reminder_ids_for_user(interaction.user.id)
        if len(ids) == 0:
            await utils.respond(interaction, "You have no reminders! Set one by using **/remind_me** or by right clicking a message and selecting **Apps -> Remind Me**")
        else:
            message = await interaction.original_response()
            view = ActiveReminderView(ids, message)
            await utils.respond(interaction, "Fetching your reminders...", view=view)
            await view.update(message, interaction.client)



# -----------------------------

    
async def setup(bot : Bot):
    await bot.add_cog(RemindMeCog(bot))