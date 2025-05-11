import traceback
from typing import Any, List, Dict, Optional, Union
import discord
from discord.ext.commands import Cog, Bot
from discord import app_commands, Interaction, Role, TextChannel, Guild, Message, PartialMessage, Member
import json
from utils import utils, db
import sqlite3
import os
import asyncio

try:
    with open("configs/roles.json", 'r') as config_json:
        config = json.load(config_json)
except Exception as e:
    utils.log("ROLES", e)
    utils.log("ROLES", "Failed to load roles cog! Config not found!")
    exit(-1)

ROLE_EMOJI : str = config["RoleEmoji"]
VOTE_EMOJI : str = config["VoteEmoji"]

db_folder_path = "data/roles"
db_path = "data/roles/roles.db"
if not os.path.exists(db_folder_path):
    os.makedirs(db_folder_path)

db_path : str = "data/roles/roles.db"
connection : sqlite3.Connection = sqlite3.connect(db_path)

# First, create all inner tables
db.execute_command(connection, """
    CREATE TABLE IF NOT EXISTS "roles" (
        name TEXT,
        desc TEXT,
        message_id INTEGER
    )               
""")
db.execute_command(connection, """
    CREATE TABLE IF NOT EXISTS "votes" (
        name TEXT,
        desc TEXT,
        message_id INTEGER,
        user_id INTEGER
    )                   
""")


delete_time = 15


def get_emoji_name(emoji_obj):
    if type(emoji_obj) is str:
        return emoji_obj
    return emoji_obj.name


class CreateARoleModal(discord.ui.Modal, title="Create a Role"):
    _nameInput = discord.ui.TextInput(label="Role Name", placeholder="Wumpuses", max_length=32)
    _descriptionInput = discord.ui.TextInput(label="Role Description", placeholder="People who like discord")

    def set_callback(self, callback):
        self.callback = callback

    async def on_submit(self, interaction: discord.Interaction):
        name = self._nameInput.value
        description = self._descriptionInput.value

        await self.callback(interaction, name, description)

class RoleData:
    def __init__(self, name:str, desc:str, message_id:int):
        self.name = name
        self.desc = desc
        self.message_id = message_id

class VoteData:
    def __init__(self, name:str, desc:str, message_id:int, user_id:int):
        self.name = name
        self.desc = desc
        self.message_id = message_id
        self.member_id = user_id



class RolesCog(Cog):

    def __init__(self, bot: Bot):
        self.bot = bot

        if self.bot.is_ready():
            utils.log("ROLES", "ON READY IN ROLES COG INIT")
            self.bot.loop.create_task(self.async_init())

    async def async_init(self):
        utils.log("ROLES", "Running Async Init for Roles")
        try:
            role_channel: TextChannel = self.get_role_channel()
            role_guild: Guild = role_channel.guild
        except Exception as role_exception:
            utils.log("ROLES", "Error grabbing role channel!")
            utils.log("ROLES", role_exception)
            return

        utils.log("ROLES", "--Creating roles and adding to saves")

        roles : List[RoleData] = db_get_all_roles()
        for role in roles:
            # Create role if it doesn't exist
            utils.log("ROLES", f"Checking role {role.name}")
            if not discord.utils.get(role_guild.roles, name=role.name):
                utils.log("ROLES", f"--Creating role {role.name}")
                await role_guild.create_role(name=role.name, mentionable=True)

            # If the role doesn't have a message, then create one
            if role.message_id is None:
                utils.log("ROLES", f"--Role {role.name} has no message id! Sending message...")
                await self.regenerate_role_message(role)
                await asyncio.sleep(5)

        role_names : List[str] = [r.name for r in roles]

        # Here's the bulk of the initialization

        # First, cache members with their saved roles
        role_member_dict : Dict[str, List[int]] = {}
        for member in role_guild.members:
            for member_role in member.roles:
                if member_role.name in role_names:
                    if member_role.name not in role_member_dict:
                        role_member_dict[member_role.name] = []
                    role_member_dict[member_role.name].append(member.id)
        
        cached_member_dict : Dict[int, Member] = {}

        # Then, loop through each of the role messages
        for role in roles:
            try:
                message_id = role.message_id
                utils.log("ROLES", f"--Grabbing message with id {int(message_id)}...")

                role_message: Message = None

                try:
                    role_message = await role_channel.fetch_message(int(message_id))
                except discord.NotFound:
                    utils.log("ROLES", f"Message for role {role} not found! Sending new one...")
                    role_message = await self.regenerate_role_message(role)
                    await asyncio.sleep(5)
                
                for role_reaction in role_message.reactions:
                    
                    emoji_name = get_emoji_name(role_reaction.emoji)

                    # Remove any emojis that aren't the active assigning one
                    if emoji_name != ROLE_EMOJI:
                        f1 = emoji_name.encode("unicode_escape")
                        f2 = ROLE_EMOJI.encode("unicode_escape")
                        utils.log("ROLES", f"Emoji mismatch! {f1} != {f2}")
                        await role_message.clear_reaction(role_reaction.emoji)
                        continue

                    utils.log("ROLES", "----Grabbing role reaction users...")
                    reaction_users = [ user async for user in role_reaction.users() ]

                    reaction_member_ids : List[int] = []
                    for reaction_user in reaction_users:
                        if type(reaction_user) is Member:
                            reaction_member_ids.append(reaction_user.id)
                        else:
                            utils.log("ROLES", f"Found non-member reaction (User {reaction_user.name})")
                            await role_reaction.remove(reaction_user)


                    # Remove roles from users who've removed their reaction on a tracked message
                    if role.name in role_member_dict:
                        for role_member_id in role_member_dict[role.name]:
                            # noinspection PyBroadException
                            try:
                                if role_member_id not in reaction_member_ids:
                                    if role_member_id not in cached_member_dict:
                                        utils.log("ROLES", "----Grabbing non-cached role member...")
                                        cached_member_dict[role_member_id] = await role_guild.fetch_member(role_member_id)
                                            
                                    role_member: Member = cached_member_dict[role_member_id]
                                    role_obj = discord.utils.get(role_guild.roles, name=role.name)
                                    await role_member.remove_roles(role_obj)
                            except Exception:
                                utils.log("ROLES", f"Error when removing role from user id {role_member_id}")
                                utils.log("ROLES", f"Exception: {traceback.print_exc()}")
                                continue

                    # Add roles from users who've added a reaction on a tracked message
                    for reaction_user_id in reaction_member_ids:
                        # noinspection PyBroadException
                        try:
                            if reaction_user_id == self.bot.user.id:
                                continue
                            if reaction_user_id not in role_member_dict:
                                if reaction_user_id not in cached_member_dict:
                                    utils.log("ROLES", "----Grabbing non-cached role member...")
                                    cached_member_dict[reaction_user_id] = await role_guild.fetch_member(reaction_user_id)
                                role_member: Member = cached_member_dict[reaction_user_id]
                                role_obj = discord.utils.get(role_guild.roles, name=role.name)
                                await role_member.add_roles(role_obj)
                        except Exception:
                            utils.log("ROLES", f"Error when getting added reaction user id {reaction_user_id}")
                            utils.log("ROLES", f"Exception: {traceback.print_exc()}")
                            continue
            except Exception:
                utils.log("ROLES", f"Error when retrieving message {message_id}")
                utils.log("ROLES", f"Exception: {traceback.print_exc()}")
                continue



        utils.log("ROLES", "Looping through saved votes.")
        votes : List[VoteData] = db_get_all_votes()
        for vote in votes:
            # noinspection PyBroadException
            try:
                msg: Message = await role_channel.fetch_message(vote.message_id)
                for msg_reaction in msg.reactions:
                    emoji_name = get_emoji_name(msg_reaction.emoji)
                    if emoji_name == VOTE_EMOJI:
                        if msg_reaction.count > config["VoteCount"]:
                            
                            await msg.delete()
                            db_remove_vote(vote.name)

                            utils.log("ROLES", f"--Creating role {vote.name}")
                            await self.add_role(vote.name, vote.desc)
                            
                    else:
                        await msg.clear_reaction(msg_reaction.emoji)
            except Exception:
                utils.log("ROLES", "Error getting vote!")
                utils.log("ROLES", f"Exception: {traceback.print_exc()}")

        #### NEW ENDS HERE

        utils.log("ROLES", "Async init completed!")

    @Cog.listener("on_ready")
    async def on_ready(self):
        utils.log("ROLES", "ON READY IN ROLES COG LISTENER")
        await self.async_init()

    # ROLE COMMANDS

    role_group = app_commands.Group(name="role", description="Commands", guild_only=True)
    
    @role_group.command(description="(Admin) Renames an existing role", extras = {"Admin": True})
    @app_commands.rename(
        old_role = "old_name",
        new_role = "new_name"
    )
    @app_commands.describe(
        old_role="Name of old role",
        new_role="Name of new role"
    )
    async def rename(self, interaction: Interaction, old_role: str, new_role: str):

        if not await self.bot.is_owner(interaction.user):
            await utils.respond(interaction, ":triumph: You're not the boss of me!", ephemeral=True)
            return

        role:RoleData = db_get_role(old_role)
        if role is None:
            await utils.respond(interaction, f"No role with the name **{old_role}** exists!", ephemeral=True)
            return

        discord_role_obj: Role = discord.utils.get(interaction.guild.roles, name=old_role)
        await discord_role_obj.edit(name=new_role)

        db_rename_role(old_role, new_role)
        await self.update_role_message(role.message_id, new_role, role.desc)

        await utils.respond(interaction, f"Renamed role **{old_role}** to **{new_role}**!", ephemeral=True)


    @role_group.command(description="(Admin) Sets the description of an existing role", extras = {"Admin": True})
    @app_commands.rename(
        role_str = "role",
        new_desc = "new_description"
    )
    @app_commands.describe(
        role_str="Name of role to adjust",
        new_desc="New description for the role"
    )
    async def set_description(self, interaction: Interaction, role_str: str, new_desc: str):

        if not await self.bot.is_owner(interaction.user):
            await utils.respond(interaction, ":triumph: You're not the boss of me!", ephemeral=True)
            return

        role:RoleData = db_get_role(role_str)
        if role is None:
            await utils.respond(interaction, f"No role with the name **{role_str}** exists!", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        db_set_description(role_str, new_desc)
        await self.update_role_message(role.message_id, role_str, new_desc)

        await utils.respond(interaction, f"Set description of role **{role_str}** to \"{new_desc}!\"", ephemeral=True)


    @role_group.command(description="(Admin) Removes a role", extras = {"Admin": True})
    @app_commands.rename(
        role_str = "role"
    )
    @app_commands.describe(
        role_str="Name of role to remove"
    )
    async def remove(self, interaction: Interaction, role_str: str):
        if not await self.bot.is_owner(interaction.user):
            await utils.respond(interaction, ":triumph: You're not the boss of me!", ephemeral=True)
            return

        role:RoleData = db_get_role(role_str)
        if role is None:
            await utils.respond(interaction, f"No role with the name **{role_str}** exists!", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)

        discord_role_obj: Role = discord.utils.get(interaction.guild.roles, name=role_str)
        await discord_role_obj.delete()

        # Remove from saved roles
        db_remove_role(role_str)

        await self.delete_role_channel_message(role.message_id)
        
        await utils.respond(interaction, f"Removed role **{role_str}**!", ephemeral=True)


    @role_group.command(description="Brings up the Create a Role modal. Users will vote on whether to add the new role.")
    async def add(self, interaction:discord.Interaction):
       modal = CreateARoleModal()
       modal.set_callback(self.on_add_modal_complete)
       await interaction.response.send_modal(modal)

    async def on_add_modal_complete(self, interaction: Interaction, role_str: str, role_desc: str):

        if db_get_role(role_str) is not None:
            await utils.respond(interaction, f"A role with the name **{role_str}** already exists!", ephemeral=True)
            return

        if db_get_vote(role_str) is not None:
            await utils.respond(interaction, f"A role with the name **{role_str}** is already being voted on!", ephemeral=True)
            return

        if discord.utils.get(interaction.guild.roles, name=role_str):
            await utils.respond(interaction, f"The name **{role_str}** is already reserved for this server!", ephemeral=True)
            return


        role_channel: TextChannel = self.get_role_channel()

        vote_str = f":ballot_box: Voting on new role **{role_str}** ({role_desc}).\n" \
                   f"This vote was initiated by {interaction.user.mention}.\n" \
                   f"React with {VOTE_EMOJI} if you want this role added!\n" \
                   f"It will be added if {config['VoteCount']} people want it. _Not including my reaction of course :)_"
        vote_message: Message = await role_channel.send(vote_str)
        await vote_message.add_reaction(VOTE_EMOJI)

        db_create_vote(role_str, role_desc, vote_message.id, interaction.user.id)

        await utils.respond(interaction, f"You started a vote for **{role_str}** here: {vote_message.jump_url}!", delete_after=delete_time)


    # noinspection PyBroadException
    @role_group.command(description="Cancels a vote (if you started vote or are admin)")
    @app_commands.rename(
        role_str = "role"
    )
    @app_commands.describe(
        role_str="Name of role to cancel vote"
    )
    async def cancel(self, interaction: Interaction, role_str: str):
        utils.log("ROLES", f"Cancel command from {interaction.user.display_name}")
        
        vote : VoteData = db_get_vote(role_str)

        if vote is None:
            await utils.respond(interaction, f"No vote exists for the role **{role_str}**!", ephemeral=True)
            return

        if vote.member_id != interaction.user.id and not await self.bot.is_owner(interaction.user):
            await utils.respond(interaction, ":triumph: You didn't start that vote and you're not the boss of me, so you can't cancel it.", ephemeral=True)
            return

        await interaction.response.defer()

        await self.delete_role_channel_message(vote.message_id)

        db_remove_vote(role_str)

        await utils.respond(interaction, f"Cancelled the vote for **{role_str}**.", delete_after=delete_time)

    @role_group.command(description="Shows help dialog")
    async def help(self, interaction: Interaction):
        with open("help/roles.json", 'r') as help_json:
            help_obj = json.load(help_json)

        help_embed: discord.Embed = discord.Embed()

        color_obj = help_obj["color"]
        help_embed.colour = discord.Color.from_rgb(color_obj["r"], color_obj["g"], color_obj["b"])

        author_obj = help_obj["author"]
        help_embed.set_author(name=author_obj["name"], icon_url=author_obj["icon_url"], url=author_obj["url"])

        help_embed.title = help_obj["title"]
        help_embed.description = help_obj["description"]

        for command in self.walk_app_commands():
            if not isinstance(command, app_commands.Group) and command.extras.get("Admin") is None:
                help_embed.add_field(name="/" + command.qualified_name, value=command.description, inline=False)

        await interaction.response.send_message(embed=help_embed)

    # LISTENERS

    @Cog.listener("on_raw_reaction_add")
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        utils.log("ROLES", "Raw reaction added!")

        # utils.log("ROLES", f"Channel id: {payload.channel_id}, Config: {config['ChannelID']}")
        if payload.channel_id != config["ChannelID"]:
            utils.log("ROLES", "--Not equal, returning")
            return

        role_member: Member = payload.member
        if self.bot.user.id == role_member.id:
            utils.log("ROLES", "--It was me!")
            return

        role_channel: TextChannel = self.bot.get_channel(payload.channel_id)
        msg: PartialMessage = role_channel.get_partial_message(payload.message_id)

        vote : VoteData = db_get_vote_by_message_id(msg.id)
        if vote is not None:
            emoji_name = get_emoji_name(payload.emoji)
            if emoji_name == VOTE_EMOJI:
                utils.log("ROLES", "--Reaction was the vote!")
                msg = await role_channel.fetch_message(payload.message_id)
                for msg_reaction in msg.reactions:
                    msg_reaction_name = get_emoji_name(msg_reaction.emoji)
                    utils.log("ROLES", f"----Msg Reaction Name: {msg_reaction_name}, emoji_name: {emoji_name}")
                    if msg_reaction_name == emoji_name:
                        utils.log("ROLES", f"----Reaction count: {msg_reaction.count}")
                        if msg_reaction.count > config["VoteCount"]:  # > since the bots reaction is there too
                            await msg.delete()
                            db_remove_vote(vote.name)
                            await self.add_role(vote.name, vote.desc)
                        break
            else:
                utils.log("ROLES", "--Wrong reaction...")
                await msg.clear_reaction(payload.emoji)
            return

        role : RoleData = db_get_role_by_message_id(msg.id)
        if role is not None:
            emoji_name = get_emoji_name(payload.emoji)

            if emoji_name == ROLE_EMOJI:
                role_obj = discord.utils.get(role_channel.guild.roles,
                                                name=role.name)
                await role_member.add_roles(role_obj)
                return
            else:
                await msg.clear_reaction(payload.emoji)


    @Cog.listener("on_raw_reaction_remove")
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        utils.log("ROLES", "Reaction removed!")

        if payload.channel_id != config["ChannelID"]:
            utils.log("ROLES", "--Wrong channel")
            return

        await self.bot.wait_until_ready()

        role_channel: TextChannel = self.bot.get_channel(payload.channel_id)

        utils.log("ROLES", "--Finding roles")
        role:RoleData = db_get_role_by_message_id(payload.message_id)
        if role is not None:
            emoji_name = get_emoji_name(payload.emoji)
            if emoji_name == ROLE_EMOJI:
                utils.log("ROLES", "--Found emoji in saved message")
                role_obj: Role = discord.utils.get(role_channel.guild.roles,
                                                    name=role.name)
                
                # noinspection PyBroadException
                try:
                    role_member: Member = await role_channel.guild.fetch_member(payload.user_id)
                except Exception:
                    utils.log("ROLES", "Error when getting role member!")
                    traceback.print_exc()
                    return
                
                await role_member.remove_roles(role_obj)

    # noinspection PyBroadException
    @Cog.listener("on_member_remove")
    async def on_member_remove(self, left_member: Member):

        utils.log("ROLES", f"User {left_member.display_name} left; updating messages")
        role_channel: TextChannel = self.get_role_channel()

        roles : list[RoleData] = db_get_all_roles()

        for role in roles:
            msg : PartialMessage = role_channel.get_partial_message(role.message_id)
            try:
                await msg.remove_reaction(ROLE_EMOJI, left_member)
            except Exception:
                utils.log("ROLES", "Exception while removing reaction from leaving user")
                utils.log("ROLES", f"Exception: {traceback.print_exc()}")

    # HELPERS

    def get_role_channel(self) -> TextChannel:
        return self.bot.get_channel(config["ChannelID"])

    async def add_role(self, name:str, desc:str):
        channel:TextChannel = self.get_role_channel()
        await channel.guild.create_role(name=name, mentionable=True)
        msg:Message = await self.send_role_message(channel, name, desc)
        db_create_role(name, desc, msg.id)

    async def regenerate_role_message(self, role:RoleData) -> Message:
        channel:TextChannel = self.get_role_channel()
        msg:Message = await self.send_role_message(channel, role.name, role.desc)
        db_set_message_id(role.name, msg.id)
        role.message_id = msg.id
        return msg

    async def send_role_message(self, channel:TextChannel, name:str, desc:str) -> Message:
        msg : Message = await channel.send(self.get_role_message_string(channel.guild, name, desc))
        await msg.add_reaction(ROLE_EMOJI)
        return msg
    
    async def update_role_message(self, message_id:int, name:str, desc:str):
        channel:TextChannel = self.get_role_channel()
        msg : PartialMessage = channel.get_partial_message(message_id)
        await msg.edit(content=self.get_role_message_string(channel.guild, name,desc))

    async def delete_role_channel_message(self, message_id:int):
        channel:TextChannel = self.get_role_channel()
        msg : PartialMessage = channel.get_partial_message(message_id)
        if msg is not None:
            await msg.delete()

    def get_role_message_string(self, guild:Guild, name:str, desc:str) -> str:
        role_obj : Role = discord.utils.get(guild.roles, name=name)
        return f"## {role_obj.mention}\n_{desc}_"

def _db_role_to_role_data(entry) -> RoleData:
    name = entry[0]
    desc = entry[1]
    message_id = entry[2]
    return RoleData(name, desc, message_id)

def _db_vote_to_vote_data(entry) -> VoteData:
    name = entry[0]
    desc = entry[1]
    message_id = entry[2]
    user_id = entry[3]
    return VoteData(name, desc, message_id, user_id)

def db_get_role(name:str) -> RoleData:
    db_role = db.get_single_row(connection, """
        SELECT * FROM roles WHERE name = ?
    """, (name,))

    if db_role is not None:
        return _db_role_to_role_data(db_role)
    return None

def db_get_role_by_message_id(message_id:int) -> RoleData:
    db_role = db.get_single_row(connection, """
        SELECT * FROM roles WHERE message_id = ?
    """, (message_id,))

    if db_role is not None:
        return _db_role_to_role_data(db_role)
    return None

def db_remove_role(name:str):
    db.execute_command(connection, """
        DELETE FROM roles WHERE name = ?
    """, (name,))

def db_get_all_roles() -> List[RoleData]:
    db_roles = db.get_data(connection, """
        SELECT * FROM roles
    """)

    out_data : List[RoleData] = []
    for db_role in db_roles:
        out_data.append(_db_role_to_role_data(db_role))
    
    print(f"{len(db_roles)} {len(out_data)}")

    return out_data

def db_get_all_votes() -> List[VoteData]:
    db_votes = db.get_data(connection, """
        SELECT * FROM votes
    """)

    out_data : List[VoteData] = []
    for db_vote in db_votes:
        out_data.append(_db_vote_to_vote_data(db_vote))

    return out_data

def db_get_vote(name:str) -> VoteData:
    db_vote = db.get_single_row(connection, """
        SELECT * FROM votes WHERE name = ?
    """, (name,))

    if db_vote is not None:
        return _db_vote_to_vote_data(db_vote)
    return None

def db_get_vote_by_message_id(message_id:int) -> VoteData:
    db_vote = db.get_single_row(connection, """
        SELECT * FROM votes WHERE message_id = ?
    """, (message_id,))

    if db_vote is not None:
        return _db_vote_to_vote_data(db_vote)
    return None

def db_remove_vote(name:str):
    db.execute_command(connection, """
        DELETE FROM votes
        WHERE name = ?
    """, (name,))

def db_create_role(name:str, desc:str, message_id:int):
    db.execute_command(connection, """
        INSERT INTO roles
        (name, desc, message_id) 
        VALUES (?, ?, ?)
    """, (name, desc, message_id))

def db_create_vote(name: str, desc:str, message_id:int, user_id:int):
    db.execute_command(connection, """
        INSERT INTO votes
        (name, desc, message_id, user_id) 
        VALUES (?, ?, ?, ?)
    """, (name, desc, message_id, user_id))

def db_role_exists(name:str) -> bool:
    return db.get_single_row(connection, """
        SELECT name FROM roles WHERE name = ?
    """, (name,)) is not None

def db_vote_exists(name:str) -> bool:
    return db.get_single_row(connection, """
        SELECT name FROM votes WHERE name = ?
    """, (name,)) is not None

def db_rename_role(old_name:str, new_name:str):
    db.execute_command(connection, """
        UPDATE roles
            SET name = ?
            WHERE name = ?;
    """, (new_name, old_name))

def db_set_description(name:str, new_desc:str):
    db.execute_command(connection, """
        UPDATE roles
        SET desc = ?
        WHERE name = ?
    """, (new_desc, name))

def db_set_message_id(name:str, message_id:int):
    db.execute_command(connection, """
        UPDATE roles 
        SET message_id = ?
        WHERE name = ?
    """, (message_id, name))

async def setup(bot : Bot):
    await bot.add_cog(RolesCog(bot))

