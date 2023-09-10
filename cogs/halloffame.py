import json
import os
import discord
from discord.ext.commands import Cog, Bot
from utils import utils, db
import sqlite3

try:
    with open("configs/halloffame.json", 'r') as config_json:
        config = json.load(config_json)
except Exception as e:
    utils.log("HALL OF FAME", e)
    utils.log("HALL OF FAME", "Failed to load halloffame cog! Config not found!")
    exit(-1)

db_folder_path = "data/halloffame"
db_path = "data/halloffame/halloffame.db"
if not os.path.exists(db_folder_path):
    os.makedirs(db_folder_path)

connection : sqlite3.Connection = sqlite3.connect(db_path)

db.execute_command(connection, """
    CREATE TABLE IF NOT EXISTS "messages" (
        original_message_id INTEGER,
        hall_message_id INTEGER
    )
""")

class HallOfFameCog(Cog):

    def __init__(self, bot: Bot):
        self.bot = bot

    @Cog.listener("on_raw_reaction_add")
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        
        utils.log("HALL OF FAME", f"Emoji added!")

        if payload.emoji.id != config["emoji_id"]:
            return
        
        # Don't hall-of-fame hall-of-fame messages
        if payload.channel_id == config["channel_id"]:
            return

        utils.log("HALL OF FAME", f"Hall of fame emoji added to message {payload.message_id} from {payload.member.display_name}")

        channel = self.bot.get_channel(payload.channel_id)
        msg = await channel.fetch_message(payload.message_id)

        count = 0
        for reaction in msg.reactions:
            if type(reaction.emoji) is not str and reaction.emoji.id == config["emoji_id"]:
                count = reaction.count
                break

        if count < config["count"]:
            return

        if self.message_in_hall_db(msg.id):
            return

        # Add message id to db first so race conditions due to async don't double-fire it
        self.add_message_to_hall_db(msg.id)
        hall_channel : discord.TextChannel = self.bot.get_channel(config["channel_id"])
        hall_msg : discord.Message = await hall_channel.send(content=f"<:halloffame:1150521160824524810> **|** {channel.jump_url}", embeds=utils.get_embeds_for_message(msg, discord.Color.from_rgb(245, 206, 66)), view=utils.get_view_for_message(msg))
        self.update_hall_db_message(msg.id, hall_msg.id)

    @Cog.listener("on_raw_message_delete")
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent):
        if payload.channel_id != config["channel_id"]:
            return
        
        utils.log("HALL OF FAME", "Message deleted!")

        db.execute_command(connection, f""" 
            DELETE FROM messages
            WHERE hall_message_id = ?
        """, (payload.message_id,))

    def message_in_hall_db(self, message_id:int):
        message = db.get_single_value(connection, f"""
            SELECT
                original_message_id
            FROM
                messages
            WHERE
                original_message_id = ?
        """, (message_id,))

        return message is not None
    
    def add_message_to_hall_db(self, original_message_id:int):
        db.execute_command(connection, f"""
            INSERT INTO messages
                (original_message_id)
                VALUES (?)
        """, (original_message_id,))

    def update_hall_db_message(self, original_message_id:int, hall_message_id:int):
        db.execute_command(connection, f"""
            UPDATE
                messages
            SET
                hall_message_id = ?
            WHERE
                original_message_id = ?
        """, (hall_message_id, original_message_id))
    



        


# -----------------------------

async def setup(bot : Bot):
    await bot.add_cog(HallOfFameCog(bot))